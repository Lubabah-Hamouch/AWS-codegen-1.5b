"""Automatic checks for the target output format.

`check_response` returns a list of failure reasons; an empty list means the response passes.
All reasons are collected (not just the first) so we can see which failures co-occur.

Target contract: the whole response is exactly one fenced Python block, the code parses, every
function/method/class has a docstring, every function is fully type-annotated, and generation
ended on its own (no truncation, no runaway repetition).
"""

import ast
import re
from collections import Counter

REASONS = (
    "truncated",
    "no_code_block",
    "multiple_code_blocks",
    "unclosed_fence",
    "non_python_block",
    "prose_before",
    "prose_after",
    "syntax_error",
    "no_definitions",
    "missing_docstring",
    "missing_param_hints",
    "missing_return_hint",
    "repetition",
)

_FENCE_LINE = re.compile(r"^[ \t]*```", re.MULTILINE)
_BLOCK = re.compile(r"^[ \t]*```([^\n`]*)\n(.*?)^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)


def extract_blocks(text: str) -> list[tuple[str, str, int, int]]:
    """Return (language, code, start, end) for each closed fenced block."""
    return [(m.group(1).strip().lower(), m.group(2), m.start(), m.end()) for m in _BLOCK.finditer(text)]


def _definitions(tree: ast.AST):
    """Functions/methods/classes at module or class level (helpers nested in functions are exempt)."""
    out = []

    def visit(node, parent_is_function):
        for child in ast.iter_child_nodes(node):
            is_fn = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            is_cls = isinstance(child, ast.ClassDef)
            if (is_fn or is_cls) and not parent_is_function:
                out.append(child)
            visit(child, parent_is_function or is_fn)

    visit(tree, False)
    return out


def _is_method(node, tree) -> bool:
    return any(isinstance(p, ast.ClassDef) and node in p.body for p in ast.walk(tree))


def _param_hints_missing(fn, is_method: bool) -> bool:
    a = fn.args
    params = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
    if is_method and params and params[0].arg in ("self", "cls"):
        params = params[1:]
    params += [x for x in (a.vararg, a.kwarg) if x is not None]
    return any(p.annotation is None for p in params)


def _has_repetition(code: str) -> bool:
    lines = [ln.strip() for ln in code.splitlines() if ln.strip()]
    if len(lines) >= 8 and len(set(lines)) / len(lines) < 0.4:
        return True
    run, prev = 0, None
    for ln in lines:
        run = run + 1 if (ln == prev and len(ln) > 3) else 1
        prev = ln
        if run >= 6:
            return True
    return False


def check_response(text: str, hit_eos: bool) -> list[str]:
    reasons: list[str] = []
    if not hit_eos:
        reasons.append("truncated")

    fence_lines = len(_FENCE_LINE.findall(text))
    blocks = extract_blocks(text)
    if fence_lines % 2 == 1:
        reasons.append("unclosed_fence")
    if not blocks:
        reasons.append("no_code_block")
        return reasons
    if len(blocks) > 1:
        reasons.append("multiple_code_blocks")

    lang, code, start, end = blocks[0]
    if lang not in ("python", "py", "python3", ""):
        reasons.append("non_python_block")
    if text[:start].strip():
        reasons.append("prose_before")
    if text[end:].strip():
        reasons.append("prose_after")

    try:
        tree = ast.parse(code)
    except SyntaxError:
        reasons.append("syntax_error")
        return reasons

    defs = _definitions(tree)
    if not defs:
        reasons.append("no_definitions")
    if any(ast.get_docstring(d) is None for d in defs):
        reasons.append("missing_docstring")
    fns = [d for d in defs if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if any(_param_hints_missing(f, _is_method(f, tree)) for f in fns):
        reasons.append("missing_param_hints")
    if any(f.returns is None and f.name != "__init__" for f in fns):
        reasons.append("missing_return_hint")
    if _has_repetition(code):
        reasons.append("repetition")
    return reasons


def summarize(results: list[list[str]]) -> dict:
    """Aggregate failure reasons over a list of per-sample reason lists."""
    n = len(results)
    counts = Counter(r for rs in results for r in rs)
    return {
        "samples": n,
        "passed": sum(1 for rs in results if not rs),
        "reason_counts": dict(counts.most_common()),
    }
