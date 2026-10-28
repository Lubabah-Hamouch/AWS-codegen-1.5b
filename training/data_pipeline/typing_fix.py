"""Generation-time mitigation for one mechanical defect: typing names used in type hints but never imported.

The shipped model sometimes writes `def f(...) -> Tuple[int, int]:` with only `from typing import List` (HumanEval/136;
5 of the 40 tuple-probe tasks). That raises NameError when the function is defined. `fix_typing_imports` adds the
missing names to the code's `from typing import` line, or inserts one, and reports what it added. It changes nothing
else, and nothing at all unless format_checks.unimported_hint_names finds a missing typing name.

This is applied to answers after generation (the playground does the same in the browser: frontend/src/lib/
typingFix.ts, kept in step by tests/test_typing_fix.py and the shared cases in typing_fix_cases.json). It is not
part of training and never edits training data.
"""

import ast
import re

from format_checks import unimported_hint_names

# Names the typing module exports that appear in type hints; the fix only ever imports these.
TYPING_NAMES = frozenset({
    "Any", "AnyStr", "AsyncGenerator", "AsyncIterable", "AsyncIterator", "Awaitable", "Callable", "ChainMap",
    "ClassVar", "Collection", "Container", "ContextManager", "Coroutine", "Counter", "DefaultDict", "Deque", "Dict",
    "Final", "FrozenSet", "Generator", "Generic", "Hashable", "IO", "ItemsView", "Iterable", "Iterator", "KeysView",
    "List", "Literal", "Mapping", "MappingView", "Match", "MutableMapping", "MutableSequence", "MutableSet",
    "NamedTuple", "NoReturn", "Optional", "OrderedDict", "Pattern", "Protocol", "Reversible", "Sequence", "Set",
    "Sized", "SupportsFloat", "SupportsIndex", "SupportsInt", "Text", "TextIO", "Tuple", "Type", "TypeVar",
    "TypedDict", "Union", "ValuesView",
})

_TYPING_LINE = re.compile(r"^from[ \t]+typing[ \t]+import[ \t]+([A-Za-z_][\w \t,]*?)[ \t]*(#.*)?$")


def fix_typing_imports(code: str) -> tuple[str, list[str]]:
    """Return (code, added_names). Code that does not parse, or needs nothing, is returned unchanged."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, []
    missing = sorted(unimported_hint_names(tree) & TYPING_NAMES)
    if not missing:
        return code, []
    lines = code.split("\n")
    for i, ln in enumerate(lines):  # extend an existing single-line `from typing import a, b`
        m = _TYPING_LINE.match(ln)
        if m:
            names = [n.strip() for n in m.group(1).split(",") if n.strip()]
            lines[i] = "from typing import " + ", ".join(names + missing) + (f"  {m.group(2)}" if m.group(2) else "")
            return "\n".join(lines), missing
    at = 0  # otherwise insert one, after any `from __future__` imports (they must come first)
    for i, ln in enumerate(lines):
        if ln.startswith("from __future__ import"):
            at = i + 1
    lines.insert(at, "from typing import " + ", ".join(missing))
    return "\n".join(lines), missing


def fix_response(text: str) -> tuple[str, list[str]]:
    """Apply the fix to the first fenced code block of a model response (the code the playground shows)."""
    from format_checks import extract_blocks

    blocks = extract_blocks(text)
    if not blocks:
        return text, []
    _, code, _, _ = blocks[0]
    fixed, added = fix_typing_imports(code)
    if not added:
        return text, []
    start = text.index(code, blocks[0][2])
    return text[:start] + fixed + text[start + len(code):], added
