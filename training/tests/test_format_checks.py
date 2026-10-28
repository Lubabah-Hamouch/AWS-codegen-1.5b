import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data_pipeline"))

from format_checks import check_response  # noqa: E402

GOOD = '''```python
def add(a: int, b: int) -> int:
    """Add two integers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        The sum.
    """
    return a + b
```'''


def reasons(text, eos=True):
    return check_response(text, eos)


def test_good_response_passes():
    assert reasons(GOOD) == []


def test_truncated_when_no_eos():
    assert "truncated" in reasons(GOOD, eos=False)


def test_prose_before_and_after():
    assert "prose_before" in reasons("Here you go:\n" + GOOD)
    assert "prose_after" in reasons(GOOD + "\nThis adds numbers.")


def test_no_code_block():
    assert reasons("def f(): pass") == ["no_code_block"]


def test_multiple_blocks():
    assert "multiple_code_blocks" in reasons(GOOD + "\n\n" + GOOD)


def test_unclosed_fence():
    assert "unclosed_fence" in reasons("```python\ndef f() -> None:\n    pass\n")


def test_non_python_block():
    assert "non_python_block" in reasons(GOOD.replace("```python", "```javascript", 1))


def test_syntax_error():
    assert reasons("```python\ndef f(:\n```") == ["syntax_error"]


def test_missing_docstring():
    code = "```python\ndef f(a: int) -> int:\n    return a\n```"
    assert reasons(code) == ["missing_docstring"]


def test_missing_hints():
    code = '```python\ndef f(a):\n    """Doc."""\n    return a\n```'
    assert set(reasons(code)) == {"missing_param_hints", "missing_return_hint"}


def test_method_self_does_not_need_hint_and_init_needs_no_return_hint():
    code = '''```python
class A:
    """Thing."""

    def __init__(self, x: int):
        """Init."""
        self.x = x

    def get(self) -> int:
        """Get x."""
        return self.x
```'''
    assert reasons(code) == []


def test_nested_helper_is_exempt():
    code = '''```python
def outer(x: int) -> int:
    """Outer."""
    def helper(y):
        return y
    return helper(x)
```'''
    assert reasons(code) == []


def test_args_kwargs_need_hints():
    code = '```python\ndef f(*args, **kwargs) -> None:\n    """Doc."""\n```'
    assert "missing_param_hints" in reasons(code)


def test_no_definitions():
    assert "no_definitions" in reasons("```python\nx = 1\n```")


def test_repetition():
    body = "\n".join(["    print('x')"] * 8)
    code = f'```python\ndef f() -> None:\n    """Doc."""\n{body}\n```'
    assert "repetition" in reasons(code)


def _hint(code):
    return reasons("```python\n" + code.strip() + "\n```")


def test_unimported_hint_name_is_flagged():
    # HumanEval/136 as the shipped model wrote it: Optional is used in the hint but never imported (NameError at def)
    code = '''
from typing import List, Tuple

def f(lst: List[int]) -> Tuple[Optional[int], Optional[int]]:
    """Doc."""
    return (None, None)
'''
    assert "unimported_hint_name" in _hint(code)


def test_imported_builtin_and_local_hint_names_pass():
    code = '''
import typing
from typing import Optional as Opt
from collections.abc import Iterable

class Node:
    """A node."""

Vector: typing.TypeAlias = list[float]
Pair = tuple[int, int]

def f(a: Opt[int], b: Iterable[str], c: "Node", d: Vector, e: Pair, *xs: int, **kw: dict) -> typing.List[bool]:
    """Doc."""
    return []
'''
    assert "unimported_hint_name" not in _hint(code)


def test_quoted_forward_reference_is_checked():
    code = '''
def f(a: "Optional[int]") -> None:
    """Doc."""
'''
    assert "unimported_hint_name" in _hint(code)


def test_star_import_is_not_guessed():
    code = '''
from typing import *

def f(a: Optional[int]) -> None:
    """Doc."""
'''
    assert "unimported_hint_name" not in _hint(code)
