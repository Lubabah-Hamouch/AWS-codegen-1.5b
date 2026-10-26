"""QLoRA fine-tuning of Qwen2.5-Coder-1.5B-Instruct on the filtered format dataset.

Run inside the training venv (see SETUP.md):
    python train.py --out ~/work/runs/v1                      # full run
    python train.py --out ~/work/runs/smoke --max-steps 30    # smoke run

Design notes (rationale for the numbers lives next to them):
- Loss is computed on the assistant response and its closing <|im_end|> only (sft_data.py).
- The same fixed prompts are generated before training (adapter disabled) and after, and both
  outputs are format-checked, for a quick qualitative before/after.
"""

import argparse
import json
import time
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from sft_data import Collator, load_split
from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainerCallback,
                          TrainingArguments, set_seed)

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "data_pipeline"))
from common import BASE_MODEL, DATA_DIR, SEED  # noqa: E402
from format_checks import check_response  # noqa: E402

# --- LoRA -------------------------------------------------------------------------------------
# Task is format adaptation (one fenced block, docstring, hints, clean stop), not new capability,
# so the adapter stays small. r=16 on all linear projections is ~18M trainable params (~1.2% of
# 1.5B): adapting every projection (attention AND MLP) matters for style/format shifts more than
# raising rank on attention alone. alpha=2r is the common scale (effective LoRA scale 2).
# Qwen2 has SEPARATE q_proj/k_proj/v_proj/o_proj and gate/up/down_proj (a fused qkv_proj, as in
# Phi-3, does not exist here, so such a target would silently match nothing). Dropout 0.05: light
# regularisation; with ~4.4k examples x 2 epochs there is little overfitting pressure.
LORA = dict(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    bias="none",
    task_type="CAUSAL_LM",
)

# Prompts for the qualitative before/after: held-out dataset prompts + extra ones without asserts.
EXTRA_PROMPTS = [
    "Write a Python function that merges two sorted lists into one sorted list.",
    "Implement a class `Stack` with push, pop and peek methods.",
    "Write a function that returns the n-th Fibonacci number.",
    "Write a Python function that checks whether a string is a palindrome, ignoring case and punctuation.",
    "Implement binary search over a sorted list and return the index of the target, or -1.",
    "Write a function that reads a CSV file and returns the rows as a list of dictionaries.",
]
N_HELD_OUT_PROMPTS = 14


@torch.inference_mode()
def sample_generations(model, tok, prompts: list[str], adapter: bool, max_new_tokens: int = 400) -> list[dict]:
    model.eval()
    out = []
    for p in prompts:
        text = tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True)
        enc = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)

        def run():
            return model.generate(**enc, do_sample=False, max_new_tokens=max_new_tokens, use_cache=True,
                                  pad_token_id=tok.pad_token_id)

        if adapter:
            gen = run()
        else:
            with model.disable_adapter():
                gen = run()
        new = gen[0][enc["input_ids"].shape[1]:].tolist()
        hit_eos = tok.convert_tokens_to_ids("<|im_end|>") in new
        resp = tok.decode(new, skip_special_tokens=True)
        out.append({"prompt": p, "response": resp, "hit_eos": hit_eos, "n_tokens": len(new),
                    "format_failures": check_response(resp, hit_eos)})
    return out


class PeakMemLog(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kw):
        if logs is not None and torch.cuda.is_available():
            logs["peak_vram_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA_DIR / "sft_train.jsonl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--max-steps", type=int, default=-1, help="override epochs (smoke run)")
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=2, help="micro-batch size (logits over the 152k vocab dominate VRAM: 8 hit 7.8 GiB, 2 uses 4.5)")
    ap.add_argument("--accum", type=int, default=8, help="gradient accumulation (effective batch = batch*accum)")
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--n-eval", type=int, default=150)
    ap.add_argument("--eval-steps", type=int, default=50)
    ap.add_argument("--save-steps", type=int, default=50, help="same as eval-steps so every eval point has a checkpoint")
    ap.add_argument("--resume", default=None, help="checkpoint dir to resume from (weights, optimizer, scheduler, data order)")
    ap.add_argument("--no-gen", action="store_true", help="skip before/after sample generations")
    args = ap.parse_args()

    set_seed(SEED)
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    train_ds, eval_ds, dropped, eval_rows = load_split(tok, args.data, args.max_len, args.n_eval, SEED)
    print(f"train {len(train_ds)}  eval {len(eval_ds)}  dropped(too long) {dropped}", flush=True)

    # Same NF4 setup as the smoke test.
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16,
                             bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, quantization_config=bnb, device_map={"": 0},
                                                 dtype=torch.bfloat16)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                            gradient_checkpointing_kwargs={"use_reentrant": False})
    model = get_peft_model(model, LoraConfig(**LORA))
    model.print_trainable_parameters()

    gen_prompts = [r["messages"][0]["content"] for r in eval_rows[:N_HELD_OUT_PROMPTS]] + EXTRA_PROMPTS
    before_path = out / "samples_before.json"
    if args.no_gen:
        before = []
    elif before_path.exists():  # resuming: greedy base-model outputs are deterministic, don't redo them
        before = json.loads(before_path.read_text(encoding="utf-8"))
    else:
        before = sample_generations(model, tok, gen_prompts, adapter=False)
        before_path.write_text(json.dumps(before, indent=2, ensure_ascii=False), encoding="utf-8")

    steps_per_epoch = len(train_ds) // (args.batch * args.accum)
    total = args.max_steps if args.max_steps > 0 else int(steps_per_epoch * args.epochs)
    targs = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.accum,
        learning_rate=args.lr,  # 2e-4: standard QLoRA value; cosine decay + short warmup keep it stable
        lr_scheduler_type="cosine",
        warmup_steps=max(1, int(0.05 * total)),
        weight_decay=0.0,
        max_grad_norm=1.0,
        optim="paged_adamw_8bit",
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=5,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=None,  # keep all (adapter-only, ~0.2 GB each) so the best-val step can be recovered
        seed=SEED,
        data_seed=SEED,
        remove_unused_columns=False,
        report_to="none",
    )
    trainer = Trainer(model=model, args=targs, train_dataset=train_ds, eval_dataset=eval_ds,
                      data_collator=Collator(tok.pad_token_id), callbacks=[PeakMemLog()])
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    result = trainer.train(resume_from_checkpoint=args.resume)
    train_s = time.time() - t0

    model.save_pretrained(out / "adapter")
    after = [] if args.no_gen else sample_generations(model, tok, gen_prompts, adapter=True)
    summary = {
        "lora": LORA, "lr": args.lr, "epochs": args.epochs, "max_steps": args.max_steps, "total_steps": total,
        "effective_batch": args.batch * args.accum, "train_examples": len(train_ds), "eval_examples": len(eval_ds),
        "dropped_too_long": dropped, "train_seconds": round(train_s, 1),
        "sec_per_step": round(train_s / max(trainer.state.global_step, 1), 2),
        "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
        "final_train_loss": result.training_loss, "log_history": trainer.state.log_history,
        "samples_before": before, "samples_after": after,
    }
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("log_history", "samples_before", "samples_after")},
                     indent=2))


if __name__ == "__main__":
    main()
