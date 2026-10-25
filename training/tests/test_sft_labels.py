"""Label-masking tests. Uses the real Qwen tokenizer (cached locally by the training setup)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sft_data import IGNORE, Collator, build_example  # noqa: E402

transformers = pytest.importorskip("transformers")
MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"

MESSAGES = [
    {"role": "user", "content": "Write a function that adds two numbers."},
    {"role": "assistant", "content": '```python\ndef add(a: int, b: int) -> int:\n    """Add."""\n    return a + b\n```'},
]


@pytest.fixture(scope="module")
def tok():
    return transformers.AutoTokenizer.from_pretrained(MODEL)


def test_eos_and_pad_are_distinct_tokens(tok):
    assert tok.convert_tokens_to_ids("<|im_end|>") != tok.pad_token_id
    assert tok.pad_token == "<|endoftext|>"


def test_eos_label_is_not_masked(tok):
    """The <|im_end|> that ends the assistant turn must be a real label, or the model never learns to stop."""
    im_end = tok.convert_tokens_to_ids("<|im_end|>")
    ex = build_example(tok, MESSAGES, max_len=1024)
    assert ex["input_ids"][-1] == im_end
    assert ex["labels"][-1] == im_end, "EOS label was masked"
    assert ex["labels"][-1] != IGNORE


def test_eos_label_survives_padding_in_batch(tok):
    """Pad one short and one long example together: pad positions are -100, the EOS of BOTH stays labeled."""
    im_end = tok.convert_tokens_to_ids("<|im_end|>")
    short = build_example(tok, MESSAGES, 1024)
    long_msgs = [MESSAGES[0], {"role": "assistant", "content": MESSAGES[1]["content"] + "\n" * 3 + "# x\n" * 50}]
    long = build_example(tok, long_msgs, 1024)
    assert len(long["input_ids"]) > len(short["input_ids"])
    batch = Collator(tok.pad_token_id)([short, long])
    pad_pos = (batch["attention_mask"][0] == 0)
    assert pad_pos.any()
    assert (batch["labels"][0][pad_pos] == IGNORE).all()
    assert (batch["input_ids"][0][pad_pos] == tok.pad_token_id).all()
    assert batch["labels"][0][len(short["input_ids"]) - 1] == im_end
    assert batch["labels"][1][-1] == im_end
    # No <|endoftext|> pad id is ever a label.
    assert not (batch["labels"] == tok.pad_token_id).any()


def test_prompt_masked_response_labeled(tok):
    ex = build_example(tok, MESSAGES, 1024)
    ids, labels = ex["input_ids"], ex["labels"]
    n_prompt = next(i for i, l in enumerate(labels) if l != IGNORE)
    assert all(l == IGNORE for l in labels[:n_prompt])
    assert labels[n_prompt:] == ids[n_prompt:]
    prompt_text = tok.decode(ids[:n_prompt])
    assert prompt_text.endswith("<|im_start|>assistant\n")
    assert "Write a function that adds two numbers." in prompt_text
    assert tok.decode(labels[n_prompt:]) == MESSAGES[1]["content"] + "<|im_end|>"


def test_matches_native_chat_template(tok):
    """Our tokenization equals the native template on the full conversation (modulo its trailing newline)."""
    ex = build_example(tok, MESSAGES, 1024)
    native = tok.apply_chat_template(MESSAGES, tokenize=False)
    assert native.endswith("<|im_end|>\n")
    assert tok.decode(ex["input_ids"]) == native[:-1]


def test_too_long_is_dropped_not_truncated(tok):
    assert build_example(tok, MESSAGES, max_len=10) is None


def test_real_dataset_example_if_present(tok):
    path = Path.home() / "work" / "data" / "sft_train.jsonl"
    if not path.exists():
        pytest.skip("dataset not present")
    im_end = tok.convert_tokens_to_ids("<|im_end|>")
    for ln, _ in zip(open(path, encoding="utf-8"), range(200)):
        ex = build_example(tok, json.loads(ln)["messages"], 4096)
        assert ex["labels"][-1] == im_end
