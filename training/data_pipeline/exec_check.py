"""Assert-execution check: run a candidate against the test block embedded in its prompt.

Many prompts end with "Your code should pass the following assertions/test case:" followed by a
fenced block of `assert` lines (sometimes with setup lines). We take the LAST fenced block of the
instruction that contains an `assert` statement and run  <candidate code> + <test block>  in a
fresh `python -I` subprocess. Exit code 0 means the asserts held.

Isolation is modest, not a security sandbox: temp working directory, empty environment, CPU/memory
rlimits and a wall-clock timeout. Run it as an unprivileged user inside WSL.
"""

import ast
import os
import re
import resource
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

from format_checks import extract_blocks

TIMEOUT_S = 5
MEM_BYTES = 1 << 30  # 1 GiB address space

_ANY_FENCE = re.compile(r"```[^\n`]*\n(.*?)```", re.DOTALL)


def extract_tests(instruction: str) -> str | None:
    """Return the test block (valid Python containing an assert) or None."""
    for code in reversed(_ANY_FENCE.findall(instruction)):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        if any(isinstance(n, ast.Assert) for n in ast.walk(tree)):
            return code
    return None


def response_code(response: str) -> str | None:
    blocks = extract_blocks(response)
    return blocks[0][1] if blocks else None


def _limits(timeout_s: int = TIMEOUT_S, mem_bytes: int = MEM_BYTES) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (timeout_s + 1, timeout_s + 1))
    os.setsid()


def run_tests(code: str, tests: str, timeout_s: int = TIMEOUT_S, mem_bytes: int = MEM_BYTES,
              env: dict | None = None) -> tuple[bool, str]:
    """Run code+tests; return (passed, short reason: ok|assertion|error|timeout)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(code + "\n\n" + tests + "\n")
        try:
            p = subprocess.run([sys.executable, "-I", path], cwd=d, env=env or {}, capture_output=True,
                               timeout=timeout_s, preexec_fn=lambda: _limits(timeout_s, mem_bytes),
                               stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return False, "timeout"
    if p.returncode == 0:
        return True, "ok"
    return False, "assertion" if b"AssertionError" in p.stderr else "error"


def run_many(jobs: list[tuple[str, str]], workers: int = 8, **kw) -> list[tuple[bool, str]]:
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda j: run_tests(*j, **kw), jobs))
