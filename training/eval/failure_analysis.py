"""Failure analysis of a scored config: the first failing test case of every task it fails, and the category table in
docs/eval_report.md ("Failure analysis"). Uses only saved outputs: no model, no generation.

    python failure_analysis.py diagnose [--config gguf_q4km]   re-run the saved answers -> failures_<config>.json
    python failure_analysis.py table    [--config gguf_q4km]   categories x (base also fails, input in prompt)

`diagnose` runs prompt + saved code + the task's tests exactly as `score` does (same sandbox and timeouts), with the
candidate wrapped to record its last call, and checks that every recorded failure reproduces. The categories in CATEGORY
are hand-assigned after reading each failure (one primary label per task; several are borderline).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data_pipeline"))
sys.path.insert(0, str(HERE))
from exec_check import _limits  # noqa: E402
from humaneval_eval import EXEC_ENV, MEM, OUT, TIMEOUT, build_program, load_tasks, pick_code  # noqa: E402

# gguf_q4km (the shipped model), 65 failing tasks (HumanEval or HumanEval+), read one by one.
CATEGORY = {
    "dropped an explicit rule": [69, 74, 75, 87, 90, 93, 101, 103, 108, 113, 120, 126, 133, 134, 137, 140, 141, 142,
                                 145, 148, 160, 163],
    "solved a familiar neighbouring problem": [6, 26, 39, 54, 109, 129, 132, 139],
    "wrong formula or algorithm": [32, 33, 38, 59, 70, 83, 100, 102, 110, 118, 130, 138, 158, 159],
    "off-by-one / boundary": [46, 121, 123, 125, 127, 135],
    "edge input (HumanEval+ only)": [22, 44, 49, 124, 154],
    "runtime error": [76, 77, 86, 95, 115, 136, 146],
    "typo-level slip": [79, 91, 117],
}

PROBE = r'''
import json as __j, sys as __s, traceback as __tb
__last = {"args": None, "out": None, "exc": None}
def __r(v, n=300):
    try: t = repr(v)
    except Exception as e: t = f"<repr failed: {e}>"
    return t if len(t) <= n else t[:n] + f"... ({len(t)} chars)"
def __wrap(f):
    def g(*a, **k):
        __last.update(args=__r(a), out=None, exc=None)
        try:
            o = f(*a, **k)
        except BaseException as e:
            __last["exc"] = f"{type(e).__name__}: {e}"[:300]
            raise
        __last["out"] = __r(o)
        return o
    return g
try:
    check(__wrap(ENTRY))
    print("__RESULT__" + __j.dumps({"kind": "pass"}))
except AssertionError:
    tb = __s.exc_info()[2]
    line = __tb.extract_tb(tb)[-1].line
    while tb.tb_next: tb = tb.tb_next
    loc = tb.tb_frame.f_locals
    print("__RESULT__" + __j.dumps({"kind": "assertion", "args": __last["args"], "got": __last["out"],
          "exp": __r(loc["exp"]) if "exp" in loc else None, "line": line}))
except BaseException as e:
    print("__RESULT__" + __j.dumps({"kind": "error", "args": __last["args"], "line": __tb.extract_tb(__s.exc_info()[2])[-1].line,
          "exc": __last["exc"] or f"{type(e).__name__}: {e}"[:300]}))
'''


def probe(program: str, tests: str, entry: str, timeout_s: int) -> dict:
    """Run like exec_check.run_tests, but report the first failing call instead of pass/fail."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(program + "\n\n" + tests + "\n" + PROBE.replace("ENTRY", entry))
        try:
            p = subprocess.run([sys.executable, "-I", path], cwd=d, env=EXEC_ENV, capture_output=True, timeout=timeout_s,
                               preexec_fn=lambda: _limits(timeout_s, MEM), stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"kind": "timeout"}
    for ln in p.stdout.decode(errors="replace").splitlines():
        if ln.startswith("__RESULT__"):
            return json.loads(ln[10:])
    return {"kind": "crash", "stderr": p.stderr.decode(errors="replace")[-400:]}  # e.g. a NameError at def time


def diagnose(config: str) -> None:
    tasks = {t["task_id"]: t for t in load_tasks()}
    rows = json.loads((OUT / f"scored_{config}.json").read_text(encoding="utf-8"))["rows"]
    out = []
    for r in rows:
        if r["pass_he"] and r["pass_heplus"]:
            continue
        t = tasks[r["task_id"]]
        code, _ = pick_code(r["response"], t["entry_point"])
        prog = build_program(t["prompt"], code)
        rec = {"task_id": r["task_id"], "entry": t["entry_point"], "pass_he": r["pass_he"], "pass_heplus": r["pass_heplus"],
               "prompt": t["prompt"], "code": code}
        rec["he"] = None if r["pass_he"] else probe(prog, t["test"], t["entry_point"], TIMEOUT["base"])
        rec["plus"] = None if r["pass_heplus"] else probe(prog, t["test_plus"], t["entry_point"], TIMEOUT["plus"])
        out.append(rec)
    passed = [x["task_id"] for x in out for k in ("he", "plus") if x[k] is not None and x[k]["kind"] == "pass"]
    assert not passed, f"recorded failures that now pass (not reproducible): {passed}"
    dest = OUT / f"failures_{config}.json"
    dest.write_text(json.dumps(out, indent=1), encoding="utf-8")
    kinds = Counter((k, x[k]["kind"]) for x in out for k in ("he", "plus") if x[k] is not None)
    print(f"{len(out)} failing tasks, all reproduce -> {dest}\n{dict(kinds)}")


def in_prompt(rec: dict) -> bool:
    """The first failing input is written in the task's own prompt as a literal call (a lower bound)."""
    norm = lambda s: re.sub(r"\s+", "", s).replace('"', "'")  # noqa: E731
    f = rec["he"] or rec["plus"]
    a = (f.get("args") or "()")[1:-1].rstrip(",")
    return bool(norm(a)) and norm(f"{rec['entry']}({a})") in norm(rec["prompt"])


def table(config: str, base: str = "base_bf16") -> None:
    fails = {r["task_id"]: r for r in json.loads((OUT / f"failures_{config}.json").read_text(encoding="utf-8"))}
    b = {r["task_id"]: r for r in json.loads((OUT / f"scored_{base}.json").read_text(encoding="utf-8"))["rows"]}
    ids = [f"HumanEval/{n}" for v in CATEGORY.values() for n in v]
    assert sorted(ids) == sorted(fails) and len(set(ids)) == len(ids), "each failing task needs exactly one category"
    print(f"| Category | Failures | Base also fails | New vs base | Failing input is in the prompt |\n|---|---|---|---|---|")
    tot = Counter()
    for cat, nums in CATEGORY.items():
        rs = [fails[f"HumanEval/{n}"] for n in nums]
        shared = sum(1 for r in rs if not (b[r["task_id"]]["pass_he"] and b[r["task_id"]]["pass_heplus"]))
        ex = sum(in_prompt(r) for r in rs)
        tot.update(n=len(rs), shared=shared, ex=ex)
        print(f"| {cat} | {len(rs)} | {shared} | {len(rs) - shared} | {ex} |")
    print(f"| **total** | **{tot['n']}** | **{tot['shared']}** | **{tot['n'] - tot['shared']}** | **{tot['ex']}** |")
    fixed = sum(1 for t, r in b.items() if not (r["pass_he"] and r["pass_heplus"]) and t not in fails)
    print(f"\n{base} fails but {config} passes: {fixed}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["diagnose", "table"])
    ap.add_argument("--config", default="gguf_q4km")
    a = ap.parse_args()
    diagnose(a.config) if a.stage == "diagnose" else table(a.config)
