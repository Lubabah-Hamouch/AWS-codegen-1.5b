"""Prompt templates. Generate mode only (explain mode is out of scope for v1).

generate.v1 sends the user's request as the sole user message and no system prompt, which is exactly the shape the
model was fine-tuned on (the Qwen chat template adds its default system message, as it did in training). The
fine-tuned model produces one fenced Python block with docstring and type hints, then stops. Adding instructions here
would move away from the training distribution and from the evaluated behaviour.
"""

VERSION = "generate.v1"
MAX_REQUEST_CHARS = 2000


class PromptError(ValueError):
    pass


def render_generate(request) -> list[dict]:
    if not isinstance(request, str):
        raise PromptError("prompt must be a string")
    text = request.strip()
    if not text:
        raise PromptError("prompt is empty")
    if len(text) > MAX_REQUEST_CHARS:
        raise PromptError(f"prompt is longer than {MAX_REQUEST_CHARS} characters")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in text):
        raise PromptError("prompt contains control characters")
    return [{"role": "user", "content": text}]
