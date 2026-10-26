import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "data_pipeline"))

from exec_check import run_tests  # noqa: E402
from humaneval_eval import EXEC_ENV, MEM, build_program, pick_code, user_message  # noqa: E402

PROMPT = '''from typing import List


def helper(x: int) -> int:
    """Double x."""
    return x * 2


def solve(xs: List[int]) -> int:
    """Return the sum of doubled values."""
'''
TEST = "def check(candidate):\n    assert candidate([1, 2]) == 6\n    assert candidate([]) == 0\n\ncheck(solve)\n"


def run(code):
    return run_tests(build_program(PROMPT, code), TEST, timeout_s=10, mem_bytes=MEM, env=EXEC_ENV)


def test_correct_solution_passes_and_can_use_prompt_helper():
    code = "def solve(xs):\n    return sum(helper(x) for x in xs)\n"
    assert run(code) == (True, "ok")


def test_wrong_solution_fails():
    assert run("def solve(xs):\n    return sum(xs)\n") == (False, "assertion")


def test_unmodified_stub_fails():
    assert run("pass")[0] is False


def test_infinite_loop_times_out():
    code = "def solve(xs):\n    while True:\n        pass\n"
    assert run_tests(build_program(PROMPT, code), TEST, timeout_s=2, mem_bytes=MEM, env=EXEC_ENV)[0] is False


def test_pick_code_prefers_block_with_entry_point():
    resp = "```python\nx = 1\n```\ntext\n```python\ndef solve(xs):\n    return 1\n```"
    code, src = pick_code(resp, "solve")
    assert "def solve" in code and src == "block_with_entry_point"


def test_pick_code_fallbacks():
    assert pick_code("```python\nx = 1\n```", "solve")[1] == "first_block"
    assert pick_code("def solve(xs):\n    return 1", "solve")[1] == "raw_text"
    assert pick_code("no code here", "solve") == (None, "no_code")


def test_same_user_message_for_all_models():
    assert user_message("def f():\n    pass\n").startswith("Complete the following Python function:")


def test_defs_only_drops_example_code_but_keeps_logic():
    from humaneval_eval import defs_only

    code = "import math\nK = 2\n\ndef solve(xs):\n    return sum(xs) * K\n\nprint(solve([1]))\nassert solve([1]) == 99\nif __name__ == '__main__':\n    solve([])\n"
    out = defs_only(code)
    assert "def solve" in out and "import math" in out and "K = 2" in out
    assert "print" not in out and "assert" not in out and "__main__" not in out
    assert defs_only("def (:") is None
