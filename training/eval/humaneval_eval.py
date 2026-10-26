"""HumanEval / HumanEval+ pass@1 (greedy) plus format compliance, for base vs fine-tuned model.

    python humaneval_eval.py gen   --config {base_bf16,base_nf4,ckpt250} [--check-bs1 N]
    python humaneval_eval.py score --config ...
    python humaneval_eval.py table                     # side-by-side summary of all scored configs

Configs (all use the same chat template, the same user message and NO format system prompt):
  base_bf16  Qwen2.5-Coder-1.5B-Instruct, bf16           the reference number
  base_nf4   same weights, 4-bit NF4 (the training-time quantisation)
  ckpt250    base_nf4 + LoRA checkpoint-250

pass@1 is greedy (one sample per task, do_sample=False), so the seed only fixes library RNGs.
Each task is generated once from the original HumanEval prompt and executed against both the
HumanEval tests and the HumanEval+ tests (same tasks, extended inputs).

Execution: program = <HumanEval prompt> + <model code> + <tests> + check(entry_point). The prompt is
included so imports and helper functions defined in it (e.g. encode_cyclic for decode_cyclic) exist;
the model's own definition then overrides the docstring-only stub. Sandboxing is the data pipeline's:
`python -I` in a temp dir, empty environment, rlimits, wall-clock timeout (see exec_check.py).
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data_pipeline"))

from exec_check import run_many  # noqa: E402
from format_checks import check_response, extract_blocks  # noqa: E402

OUT = Path.home() / "work" / "eval"
SEED = 42
ADAPTER = Path.home() / "work" / "runs" / "v1" / "checkpoints" / "checkpoint-250"
CONFIGS = ("base_bf16", "base_nf4", "ckpt250")
EXEC_ENV = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
TIMEOUT = {"base": 10, "plus": 40}  # HumanEval+ has up to ~500 KB of test inputs per task
MEM = 4 << 30


def user_message(prompt: str) -> str:
    return f"Complete the following Python function:\n\n```python\n{prompt.strip()}\n```"


def load_tasks():
    from datasets import load_dataset

    he = load_dataset("openai/openai_humaneval", split="test")
    plus = {r["task_id"]: r for r in load_dataset("evalplus/humanevalplus", split="test")}
    tasks = []
    for r in he:
        p = plus[r["task_id"]]
        assert p["entry_point"] == r["entry_point"]
        tasks.append({"task_id": r["task_id"], "prompt": r["prompt"], "entry_point": r["entry_point"],
                      "test": r["test"], "test_plus": p["test"], "prompt_plus_differs": p["prompt"] != r["prompt"]})
    return tasks


# --------------------------------------------------------------------------- generation
def generate(config: str, check_bs1: int, batch: int, max_new_tokens: int) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, set_seed

    from common import BASE_MODEL

    set_seed(SEED)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, padding_side="left")
    kw = {"dtype": torch.bfloat16, "device_map": {"": 0}}
    if config != "base_bf16":
        kw["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, **kw)
    if config == "ckpt250":
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, str(ADAPTER))
    model.eval()
    im_end = tok.convert_tokens_to_ids("<|im_end|>")

    tasks = load_tasks()
    texts = [tok.apply_chat_template([{"role": "user", "content": user_message(t["prompt"])}], tokenize=False,
                                     add_generation_prompt=True) for t in tasks]

    def run(idx: list[int]) -> dict[int, dict]:
        enc = tok([texts[i] for i in idx], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
        with torch.inference_mode():
            gen = model.generate(**enc, do_sample=False, max_new_tokens=max_new_tokens, pad_token_id=tok.pad_token_id)
        res = {}
        for row, i in zip(gen[:, enc["input_ids"].shape[1]:].tolist(), idx):
            hit = im_end in row
            cut = row.index(im_end) if hit else len(row)
            ids = row[:cut]
            while ids and ids[-1] == tok.pad_token_id:  # pads only follow EOS, but stay safe if EOS was never hit
                ids.pop()
            res[i] = {"response": tok.decode(ids, skip_special_tokens=True), "hit_eos": hit, "n_tokens": len(ids)}
        return res

    t0 = time.time()
    order = sorted(range(len(tasks)), key=lambda i: len(texts[i]))
    results: dict[int, dict] = {}
    for b in range(0, len(order), batch):
        results.update(run(order[b : b + batch]))
        print(f"[{config}] {len(results)}/{len(tasks)}  {time.time() - t0:.0f}s", flush=True)
    gen_s = time.time() - t0

    # Batched greedy decoding with left padding can differ slightly from single-sequence decoding
    # (bf16 numerics); measure how much on the first N tasks.
    agree = None
    if check_bs1:
        same = sum(run([i])[i]["response"] == results[i]["response"] for i in range(check_bs1))
        agree = {"checked": check_bs1, "identical_to_batch_size_1": same}
        print(f"[{config}] batch-vs-single agreement: {same}/{check_bs1}", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    recs = [{"task_id": t["task_id"], **results[i]} for i, t in enumerate(tasks)]
    (OUT / f"gen_{config}.json").write_text(json.dumps(
        {"config": config, "seed": SEED, "greedy": True, "max_new_tokens": max_new_tokens, "batch": batch,
         "gen_seconds": round(gen_s, 1), "bs1_agreement": agree, "records": recs}, indent=1, ensure_ascii=False),
        encoding="utf-8")


# --------------------------------------------------------------------------- scoring
def pick_code(response: str, entry_point: str) -> tuple[str | None, str]:
    """Code to execute. Prefer the first fenced block that defines the entry point; fall back to the
    first block, then to the raw text if it parses. Same rule for every model."""
    blocks = [b[1] for b in extract_blocks(response)]
    for b in blocks:
        if re.search(rf"def\s+{re.escape(entry_point)}\b", b):
            return b, "block_with_entry_point"
    if blocks:
        return blocks[0], "first_block"
    if re.search(rf"def\s+{re.escape(entry_point)}\b", response):
        return response, "raw_text"
    return None, "no_code"


def defs_only(code: str) -> str | None:
    """Keep imports, function/class definitions and simple assignments; drop module-level statements such as
    example calls, prints and `if __name__` blocks. Separates "is the function right" from "did the model add
    extra top-level code". None if the code does not parse."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    keep = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign)
    tree.body = [n for n in tree.body if isinstance(n, keep)]
    return ast.unparse(tree)


def build_program(prompt: str, code: str) -> str:
    return prompt + "\n\n" + code


def score(config: str) -> dict:
    tasks = {t["task_id"]: t for t in load_tasks()}
    data = json.loads((OUT / f"gen_{config}.json").read_text(encoding="utf-8"))
    recs = data["records"]
    codes = [pick_code(r["response"], tasks[r["task_id"]]["entry_point"]) for r in recs]

    def jobs(kind: str, defs: bool = False):
        out, idx = [], []
        for i, (r, (code, _)) in enumerate(zip(recs, codes)):
            if code is not None and defs:
                code = defs_only(code)
            if code is None:
                continue
            t = tasks[r["task_id"]]
            tests = t["test"] if kind == "base" else t["test_plus"]
            out.append((build_program(t["prompt"], code), tests + f"\n\ncheck({t['entry_point']})\n"))
            idx.append(i)
        return out, idx

    res = {}
    for kind in ("base", "plus"):
        j, idx = jobs(kind)
        t0 = time.time()
        got = run_many(j, workers=8, timeout_s=TIMEOUT[kind], mem_bytes=MEM, env=EXEC_ENV)
        print(f"[{config}] exec {kind}: {len(j)} programs in {time.time() - t0:.0f}s", flush=True)
        res[kind] = dict(zip(idx, got))
        j, idx = jobs(kind, defs=True)
        res[kind + "_defs"] = dict(zip(idx, run_many(j, workers=8, timeout_s=TIMEOUT[kind], mem_bytes=MEM, env=EXEC_ENV)))

    rows = []
    for i, r in enumerate(recs):
        fmt = check_response(r["response"], r["hit_eos"])
        rows.append({**r, "code_source": codes[i][1], "format_failures": fmt, "format_ok": not fmt,
                     "pass_he": res["base"].get(i, (False, "no_code"))[0],
                     "he_reason": res["base"].get(i, (False, "no_code"))[1],
                     "pass_he_defs": res["base_defs"].get(i, (False, "no_code"))[0],
                     "pass_heplus_defs": res["plus_defs"].get(i, (False, "no_code"))[0],
                     "pass_heplus": res["plus"].get(i, (False, "no_code"))[0],
                     "heplus_reason": res["plus"].get(i, (False, "no_code"))[1]})
    n = len(rows)
    summ = {
        "config": config, "n_tasks": n, "gen_seconds": data["gen_seconds"], "bs1_agreement": data["bs1_agreement"],
        "pass@1_humaneval": sum(r["pass_he"] for r in rows) / n,
        "pass@1_humaneval_plus": sum(r["pass_heplus"] for r in rows) / n,
        "pass@1_humaneval_defs_only": sum(r["pass_he_defs"] for r in rows) / n,
        "pass@1_humaneval_plus_defs_only": sum(r["pass_heplus_defs"] for r in rows) / n,
        "format_clean": sum(r["format_ok"] for r in rows) / n,
        "stopped_on_eos": sum(r["hit_eos"] for r in rows) / n,
        "mean_tokens": sum(r["n_tokens"] for r in rows) / n,
        "format_failure_counts": dict(Counter(f for r in rows for f in r["format_failures"]).most_common()),
        "code_source": dict(Counter(r["code_source"] for r in rows)),
        "he_fail_reasons": dict(Counter(r["he_reason"] for r in rows if not r["pass_he"])),
        "crosstab_humaneval": {
            "format_ok&pass": sum(r["format_ok"] and r["pass_he"] for r in rows),
            "format_ok&fail": sum(r["format_ok"] and not r["pass_he"] for r in rows),
            "format_bad&pass": sum((not r["format_ok"]) and r["pass_he"] for r in rows),
            "format_bad&fail": sum((not r["format_ok"]) and not r["pass_he"] for r in rows)},
    }
    (OUT / f"scored_{config}.json").write_text(json.dumps({"summary": summ, "rows": rows}, indent=1, ensure_ascii=False),
                                              encoding="utf-8")
    print(json.dumps(summ, indent=1))
    return summ


def table() -> None:
    cols = [json.loads((OUT / f"scored_{c}.json").read_text(encoding="utf-8"))["summary"]
            for c in CONFIGS if (OUT / f"scored_{c}.json").exists()]
    print(f"{'':28}" + "".join(f"{c['config']:>12}" for c in cols))
    for key in ("pass@1_humaneval", "pass@1_humaneval_plus", "pass@1_humaneval_defs_only",
                "pass@1_humaneval_plus_defs_only", "format_clean", "stopped_on_eos"):
        print(f"{key:28}" + "".join(f"{c[key] * 100:11.1f}%" for c in cols))
    print(f"{'mean_tokens':28}" + "".join(f"{c['mean_tokens']:12.0f}" for c in cols))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["gen", "score", "table"])
    ap.add_argument("--config", choices=CONFIGS)
    ap.add_argument("--check-bs1", type=int, default=0)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-new-tokens", type=int, default=768)
    a = ap.parse_args()
    if a.stage == "gen":
        generate(a.config, a.check_bs1, a.batch, a.max_new_tokens)
    elif a.stage == "score":
        score(a.config)
    else:
        table()


if __name__ == "__main__":
    main()
