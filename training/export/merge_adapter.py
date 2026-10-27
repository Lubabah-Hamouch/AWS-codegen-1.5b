"""Merge a LoRA adapter into the bf16 base model and save a standalone HF model.

    python merge_adapter.py --adapter ~/work/runs/v1/checkpoints/checkpoint-250 --out ~/work/export/merged_ckpt250

Note on precision: the adapter was trained on top of the 4-bit NF4 weights, but it is merged into the
original bf16 weights (the standard QLoRA merge; a GGUF export needs full-precision weights anyway). The
merged model therefore differs slightly from "NF4 base + adapter"; the eval harness measures the merged
model directly instead of assuming the two are equivalent.

The script verifies the merge: next-token logits of (bf16 base + unmerged adapter) must match the merged
model on a few prompts.
"""

import argparse
import json
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data_pipeline"))
from common import BASE_MODEL  # noqa: E402

CHECK_PROMPTS = [
    "Write a Python function that returns the nth Fibonacci number.",
    "Complete the following Python function:\n\n```python\ndef add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n```",
    "Implement a class `Stack` with push, pop and peek methods.",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.bfloat16, device_map={"": 0})
    model = PeftModel.from_pretrained(base, str(Path(a.adapter).expanduser())).eval()

    def logits(m):
        res = []
        for p in CHECK_PROMPTS:
            text = tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True)
            enc = tok(text, return_tensors="pt", add_special_tokens=False).to("cuda")
            with torch.inference_mode():
                res.append(m(**enc).logits[0, -1].float().cpu())
        return res

    before = logits(model)  # adapter applied at runtime
    n_lora = sum(p.numel() for n, p in model.named_parameters() if "lora_" in n)
    merged = model.merge_and_unload()
    assert not any("lora_" in n for n, _ in merged.named_parameters()), "LoRA weights still present after merge"
    after = logits(merged)

    report = {"adapter": a.adapter, "lora_params_merged": n_lora, "prompts": []}
    for p, b, m in zip(CHECK_PROMPTS, before, after):
        report["prompts"].append({"prompt": p[:60], "max_abs_logit_diff": round((b - m).abs().max().item(), 4),
                                  "same_top1": int(b.argmax()) == int(m.argmax()),
                                  "top5_overlap": len(set(b.topk(5).indices.tolist()) & set(m.topk(5).indices.tolist()))})
    print(json.dumps(report, indent=1))
    assert all(r["same_top1"] for r in report["prompts"]), "merged model disagrees with unmerged adapter"

    merged.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    (out / "merge_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("saved", out)


if __name__ == "__main__":
    main()
