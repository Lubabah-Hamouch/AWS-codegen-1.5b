"""Tokenization, label masking and batching for assistant-only SFT.

Layout of one example (plain user instruction, no custom system prompt, so Qwen's native chat
template supplies its default system message, exactly as at inference):

    <|im_start|>system ... <|im_end|> <|im_start|>user ... <|im_end|> <|im_start|>assistant\n   <- label -100
    ```python ... ```<|im_end|>                                                               <- real labels

Labels:
- prompt tokens (system + user + assistant header): -100
- assistant response AND the closing <|im_end|> (the EOS the model must learn to emit): real ids
- padding (<|endoftext|>): -100, applied by the collator on padded positions only. Labels are never
  masked by comparing token ids against the pad id, so a real EOS can never be masked by accident.

The template's trailing "\\n" after the final <|im_end|> is not part of the example: generation
stops at <|im_end|>. Examples longer than max_len are dropped, not truncated, so the EOS label can
never be cut off.
"""

import json
import random
from pathlib import Path

import torch

IGNORE = -100
IM_END = "<|im_end|>"


def build_example(tok, messages: list[dict], max_len: int) -> dict | None:
    """messages = [user, assistant]. Returns input_ids/labels or None if longer than max_len."""
    user, assistant = messages
    prompt_text = tok.apply_chat_template([user], tokenize=False, add_generation_prompt=True)
    prompt_ids = tok(prompt_text, add_special_tokens=False)["input_ids"]
    resp_ids = tok(assistant["content"] + IM_END, add_special_tokens=False)["input_ids"]
    if resp_ids[-1] != tok.convert_tokens_to_ids(IM_END):
        raise ValueError("response does not end in a single <|im_end|> token")
    if len(prompt_ids) + len(resp_ids) > max_len:
        return None
    return {"input_ids": prompt_ids + resp_ids, "labels": [IGNORE] * len(prompt_ids) + resp_ids}


def load_split(tok, path: str | Path, max_len: int, n_eval: int, seed: int):
    """Seeded shuffle, hold out n_eval examples. Returns (train, eval, n_dropped_too_long, eval_rows)."""
    rows = [json.loads(ln) for ln in open(path, encoding="utf-8")]
    random.Random(seed).shuffle(rows)
    built, dropped = [], 0
    for r in rows:
        ex = build_example(tok, r["messages"], max_len)
        if ex is None:
            dropped += 1
        else:
            built.append((r, ex))
    held = built[:n_eval]
    return [e for _, e in built[n_eval:]], [e for _, e in held], dropped, [r for r, _ in held]


class Collator:
    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, batch: list[dict]) -> dict:
        n = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), n), self.pad_id, dtype=torch.long)
        labels = torch.full((len(batch), n), IGNORE, dtype=torch.long)
        mask = torch.zeros((len(batch), n), dtype=torch.long)
        for i, b in enumerate(batch):
            k = len(b["input_ids"])
            ids[i, :k] = torch.tensor(b["input_ids"])
            labels[i, :k] = torch.tensor(b["labels"])
            mask[i, :k] = 1
        return {"input_ids": ids, "labels": labels, "attention_mask": mask}
