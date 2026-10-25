import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data_pipeline"))

from exec_check import extract_tests, response_code, run_tests  # noqa: E402

PROMPT = """Write add.

Your code should pass the following assertions:
```python
assert add(1, 2) == 3
assert add(0, 0) == 0
```"""


def test_extract_tests_takes_assert_block():
    assert "assert add(1, 2) == 3" in extract_tests(PROMPT)


def test_extract_tests_none_without_asserts():
    assert extract_tests("Write a function.\n```python\nx = 1\n```") is None
    assert extract_tests("Write a function.") is None


def test_extract_tests_keeps_setup_lines():
    p = "Do it.\n```python\nx = [1]\nr = f(x)\nassert r == 1\n```"
    assert "x = [1]" in extract_tests(p)


def test_response_code():
    assert response_code("```python\nx = 1\n```") == "x = 1\n"


def test_run_pass_fail_error_timeout():
    t = extract_tests(PROMPT)
    assert run_tests("def add(a, b):\n    return a + b", t) == (True, "ok")
    assert run_tests("def add(a, b):\n    return a - b", t) == (False, "assertion")
    assert run_tests("def other(): pass", t) == (False, "error")
    assert run_tests("def add(a, b):\n    while True: pass", t)[1] in ("timeout", "error")
