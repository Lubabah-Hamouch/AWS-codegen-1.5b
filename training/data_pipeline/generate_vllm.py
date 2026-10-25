"""vLLM version of generate.py: same prompts, same system prompt, same output schema.

Runs from a separate venv (~/venvs/vllm) so the pinned training requirements stay untouched.
Writes the output file once at the end of each chunk (--chunk prompts), so a long run can resume.
"""

import argparse
import json
import random
import time
from pathlib import Path

from common import BASE_MODEL, DATA_DIR, SEED
from format_spec import SYSTEM_PROMPT
from vllm import LLM, SamplingParams

TEMPERATURE = 0.8
TOP_P = 0.95


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", default=str(DATA_DIR / "prompts_with_tests.jsonl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("-n", type=int, default=4)
    ap.add_argument("--max-new-tokens", type=int, default=768)
    ap.add_argument("--chunk", type=int, default=500, help="prompts per write/resume unit")
    ap.add_argument("--gpu-mem", type=float, default=0.6)
    ap.add_argument("--eager", action="store_true", help="disable CUDA graphs (avoids a capture-time stall on 8 GB GPUs)")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    rows = [json.loads(ln) for ln in open(args.prompts, encoding="utf-8")]
    random.Random(args.seed).shuffle(rows)
    rows = rows[: args.limit] if args.limit else rows
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.loads(ln)["id"] for ln in open(out, encoding="utf-8")}
    todo = [r for r in rows if r["id"] not in done]
    print(f"{len(rows)} prompts selected, {len(todo)} to do", flush=True)

    t_load = time.time()
    llm = LLM(BASE_MODEL, dtype="bfloat16", gpu_memory_utilization=args.gpu_mem, max_model_len=2048, seed=args.seed,
              enforce_eager=args.eager)
    print(f"model load {time.time() - t_load:.0f}s", flush=True)
    tok = llm.get_tokenizer()
    sp = SamplingParams(n=args.n, temperature=TEMPERATURE, top_p=TOP_P, max_tokens=args.max_new_tokens, seed=args.seed)

    def render(instr: str) -> str:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": instr}]
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

    t0, n_tok, n_samples = time.time(), 0, 0
    for i in range(0, len(todo), args.chunk):
        chunk = todo[i : i + args.chunk]
        outs = llm.generate([render(r["instruction"]) for r in chunk], sp, use_tqdm=False)
        with open(out, "a", encoding="utf-8") as f:
            for r, o in zip(chunk, outs):
                for j, c in enumerate(o.outputs):
                    n_tok += len(c.token_ids)
                    n_samples += 1
                    f.write(json.dumps({"id": r["id"], "instruction": r["instruction"], "sample": j, "response": c.text,
                                        "hit_eos": c.finish_reason == "stop", "n_tokens": len(c.token_ids)},
                                       ensure_ascii=False) + "\n")
        el = time.time() - t0
        print(f"[{n_samples} samples] {el:.0f}s  {n_tok / el:.0f} tok/s  {n_samples / el:.2f} samples/s", flush=True)
    el = time.time() - t0
    print(json.dumps({"samples": n_samples, "seconds": round(el, 1), "gen_tokens": n_tok,
                      "tok_per_s": round(n_tok / max(el, 1e-9), 1)}))


if __name__ == "__main__":
    main()
