"""Step 4: sample N responses per prompt from the base model under the format system prompt.

Output is append-only JSONL (one line per sample) so an interrupted run resumes where it
stopped: prompts that already have N samples in the output file are skipped.
"""

import argparse
import json
import random
import time

import torch
from common import BASE_MODEL, DATA_DIR, SEED, ensure_data_dir
from format_spec import SYSTEM_PROMPT
from transformers import AutoModelForCausalLM, AutoTokenizer

# Sampling: temperature 0.8 / top_p 0.95 gives enough diversity that the N samples differ, while
# the system prompt keeps the format stable. repetition_penalty stays at 1.0 so we measure the
# model's real tendency to loop rather than hiding it.
TEMPERATURE = 0.8
TOP_P = 0.95


def load_prompts(path, limit, seed):
    rows = [json.loads(ln) for ln in open(path, encoding="utf-8")]
    random.Random(seed).shuffle(rows)
    return rows[:limit] if limit else rows


def done_counts(path):
    counts = {}
    if path.exists():
        for ln in open(path, encoding="utf-8"):
            pid = json.loads(ln)["id"]
            counts[pid] = counts.get(pid, 0) + 1
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", default=str(DATA_DIR / "prompts.jsonl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="number of prompts (0 = all)")
    ap.add_argument("-n", type=int, default=4, help="samples per prompt")
    ap.add_argument("--prompt-batch", type=int, default=16, help="prompts per generate() call")
    ap.add_argument("--max-new-tokens", type=int, default=768)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    ensure_data_dir()
    from pathlib import Path

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prompts = load_prompts(args.prompts, args.limit, args.seed)
    have = done_counts(out)
    todo = [p for p in prompts if have.get(p["id"], 0) < args.n]
    print(f"{len(prompts)} prompts selected, {len(todo)} to do", flush=True)

    tok = AutoTokenizer.from_pretrained(BASE_MODEL, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.bfloat16, device_map="cuda").eval()
    eos_ids = {tok.convert_tokens_to_ids("<|im_end|>"), tok.convert_tokens_to_ids("<|endoftext|>")}
    torch.manual_seed(args.seed)

    def render(instr):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": instr}]
        return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

    # Length-sort so each batch pads little.
    todo.sort(key=lambda p: len(p["instruction"]))
    t0, n_tok, n_samples = time.time(), 0, 0
    with open(out, "a", encoding="utf-8") as f:
        for i in range(0, len(todo), args.prompt_batch):
            batch = todo[i : i + args.prompt_batch]
            enc = tok([render(p["instruction"]) for p in batch], return_tensors="pt", padding=True).to("cuda")
            with torch.inference_mode():
                gen = model.generate(
                    **enc,
                    do_sample=True,
                    temperature=TEMPERATURE,
                    top_p=TOP_P,
                    num_return_sequences=args.n,
                    max_new_tokens=args.max_new_tokens,
                    pad_token_id=tok.pad_token_id,
                )
            new = gen[:, enc["input_ids"].shape[1] :].cpu()
            for j, seq in enumerate(new):
                p = batch[j // args.n]
                ids = seq.tolist()
                hit_eos = any(t in eos_ids for t in ids)
                cut = next((k for k, t in enumerate(ids) if t in eos_ids), len(ids))
                n_tok += cut
                text = tok.decode(ids[:cut], skip_special_tokens=True)
                f.write(json.dumps({"id": p["id"], "instruction": p["instruction"], "sample": j % args.n,
                                    "response": text, "hit_eos": hit_eos, "n_tokens": cut}, ensure_ascii=False) + "\n")
                n_samples += 1
            f.flush()
            el = time.time() - t0
            print(f"[{n_samples} samples] {el:.0f}s  {n_tok / el:.0f} tok/s  {n_samples / el:.2f} samples/s", flush=True)
    el = time.time() - t0
    print(json.dumps({"samples": n_samples, "seconds": round(el, 1), "gen_tokens": n_tok,
                      "tok_per_s": round(n_tok / max(el, 1e-9), 1)}))


if __name__ == "__main__":
    main()
