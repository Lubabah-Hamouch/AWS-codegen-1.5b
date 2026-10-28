"""Tuple-immutability probe (probes/tuple_tasks.py): do the models treat tuples as mutable?

    python tuple_probe.py validate                                   references pass, mutants get the right label
    python tuple_probe.py gen   --name gguf_q4km --gguf <model.gguf>  greedy answers via llama-server (CPU)
    python tuple_probe.py score --name gguf_q4km                      label every answer
    python tuple_probe.py table base_q4km gguf_q4km                   compare runs

Prompts are sent exactly as the playground sends them (generate.v1: the request as the only user message, no system
prompt), greedy, max 512 tokens: the deployed configuration. Each answer gets one outcome, from its first failing case:
  correct                 every case returns the expected value
  tuple_item_assignment   TypeError: 'tuple' object does not support item assignment (the merge_intervals bug)
  tuple_other_mutation    another attempt to change a tuple in place (.append, .sort, del t[i], ...)
  container_type          right values, wrong container (e.g. lists where tuples were asked for)
  wrong_answer / error / timeout / no_code
and a separate flag, mutated_input, when a call changed the caller's arguments (lists sorted in place, etc.).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data_pipeline"))
sys.path.insert(0, str(HERE))
from exec_check import _limits  # noqa: E402
from format_checks import extract_blocks  # noqa: E402
from humaneval_eval import EXEC_ENV, LLAMA_SERVER, MEM, OUT, SEED, defs_only  # noqa: E402
from probes.tuple_tasks import MUTANTS, RAISES, TASKS  # noqa: E402

MAX_TOKENS = 512  # the playground's limit
TIMEOUT_S = 10

RUNNER = r'''
import copy as __copy, json as __json
RAISES = "__raises__:"
def __norm(x):
    return tuple(__norm(v) for v in x) if isinstance(x, (list, tuple)) else x
def __same(a, b, strict):
    """Equal, with floats compared to 1e-9 relative; strict also requires the same container types throughout."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return (not strict or type(a) is type(b)) and len(a) == len(b) and all(__same(x, y, strict) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
        except TypeError:
            return False
    return (not strict or type(a) is type(b) or {type(a), type(b)} <= {int, float, bool}) and a == b
def __kind(e):
    m = str(e)
    if isinstance(e, TypeError) and "'tuple' object does not support item assignment" in m:
        return "tuple_item_assignment"
    if ("'tuple' object has no attribute" in m) or ("'tuple' object doesn't support item deletion" in m) \
            or ("'tuple' object does not support item deletion" in m):
        return "tuple_other_mutation"
    return "error"
__out = []
for __args, __exp in CASES:
    __snap = __copy.deepcopy(__args)
    r = {"args": repr(__args)[:200], "exp": repr(__exp)[:200]}
    try:
        __got = ENTRY(*__args)
    except Exception as __e:
        if isinstance(__exp, str) and __exp == RAISES + type(__e).__name__:
            r["kind"] = "correct"
        else:
            r["kind"], r["exc"] = __kind(__e), f"{type(__e).__name__}: {__e}"[:200]
    else:
        r["got"] = repr(__got)[:200]
        if isinstance(__exp, str) and __exp.startswith(RAISES):
            r["kind"] = "wrong_answer"
        elif __same(__got, __exp, True):
            r["kind"] = "correct"
        elif __same(__got, __exp, False):
            r["kind"] = "container_type"
        else:
            r["kind"] = "wrong_answer"
    r["mutated_input"] = __args != __snap
    __out.append(r)
print("__RESULT__" + __json.dumps(__out))
'''
ORDER = ["tuple_item_assignment", "tuple_other_mutation", "error", "container_type", "wrong_answer"]


def code_of(response: str) -> str | None:
    blocks = [c for lang, c, _, _ in extract_blocks(response) if lang in ("python", "py", "python3", "")]
    return blocks[0] if blocks else None


def crash_kind(stderr: str) -> str:
    """Same labels as the in-sandbox runner, for a crash before any case ran."""
    last = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    if "'tuple' object does not support item assignment" in last:
        return "tuple_item_assignment"
    if "'tuple' object has no attribute" in last or "'tuple' object doesn't support item deletion" in last:
        return "tuple_other_mutation"
    return "error"


def run(code: str, task: dict) -> dict:
    """Label one answer: the worst case kind (in ORDER) decides; mutated_input is reported separately.

    Only definitions run (imports, functions, classes, assignments; humaneval_eval's "definitions only"): models, the
    base one especially, append example calls that would otherwise run, and can crash, before any test case. An
    example kept as an assignment (`result = f(x)`) still runs; a crash there is labelled by crash_kind."""
    code = defs_only(code) or code
    prog = code + "\n\n" + f"CASES = {task['cases']!r}\nENTRY = {task['entry']}\n" + RUNNER
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.py")
        Path(path).write_text(prog, encoding="utf-8")
        try:
            p = subprocess.run([sys.executable, "-I", path], cwd=d, env=EXEC_ENV, capture_output=True, timeout=TIMEOUT_S,
                               preexec_fn=lambda: _limits(TIMEOUT_S, MEM), stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"outcome": "timeout", "mutated_input": False, "cases": []}
    line = next((ln for ln in p.stdout.decode(errors="replace").splitlines() if ln.startswith("__RESULT__")), None)
    if line is None:  # crashed before the cases ran: NameError at definition, missing entry point, ...
        err = p.stderr.decode(errors="replace")
        return {"outcome": crash_kind(err), "mutated_input": False, "cases": [], "stderr": err[-300:]}
    cases = json.loads(line[10:])
    kinds = {c["kind"] for c in cases}
    outcome = next((k for k in ORDER if k in kinds), "correct")
    return {"outcome": outcome, "mutated_input": any(c["mutated_input"] for c in cases), "cases": cases}


def validate() -> None:
    assert len(TASKS) == 40 and len({t["id"] for t in TASKS}) == 40, "40 tasks, unique ids"
    bad = []
    for t in TASKS:
        r = run(t["reference"], t)
        if r["outcome"] != "correct" or r["mutated_input"]:
            bad.append((t["id"], r["outcome"], [c for c in r["cases"] if c["kind"] != "correct"][:1]))
    print(f"references: {40 - len(bad)}/40 correct, none mutating their input", *bad, sep="\n  ")
    by_id = {t["id"]: t for t in TASKS}
    for tid, want, code in MUTANTS:
        r = run(code, by_id[tid])
        got = "mutated_input" if want == "mutated_input" and r["mutated_input"] else r["outcome"]
        print(f"mutant {tid:16s} expected {want:22s} got {got:22s} {'OK' if got == want else 'MISMATCH'}")
        bad += [] if got == want else [(tid, want, got)]
    sys.exit(1 if bad else 0)


def gen(name: str, gguf: str, threads: int, parallel: int) -> None:
    port = 8090
    log = open(OUT / f"probe_tuples_{name}.server.log", "w")
    env = {"LD_LIBRARY_PATH": f"{LLAMA_SERVER.parent}:{LLAMA_SERVER.parents[2] / 'lib'}", "PATH": "/usr/bin:/bin"}
    srv = subprocess.Popen([str(LLAMA_SERVER), "-m", gguf, "--port", str(port), "--host", "127.0.0.1", "-t", str(threads),
                            "--parallel", str(parallel), "-c", str(2048 * parallel), "--jinja", "--no-webui"],
                           stdout=log, stderr=log, env=env)

    def one(t: dict) -> dict:
        body = {"messages": [{"role": "user", "content": t["prompt"]}], "temperature": 0, "top_k": 1, "seed": SEED,
                "max_tokens": MAX_TOKENS}
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=900))
        ch = r["choices"][0]
        return {"id": t["id"], "response": ch["message"]["content"], "hit_eos": ch["finish_reason"] == "stop",
                "n_tokens": r["usage"]["completion_tokens"]}

    try:
        for _ in range(180):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
                break
            except Exception:
                if srv.poll() is not None:
                    raise RuntimeError("llama-server exited; see the server log")
                time.sleep(2)
        t0 = time.time()
        with ThreadPoolExecutor(parallel) as ex:
            recs = list(ex.map(one, TASKS))
        gen_s = time.time() - t0
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=20)
        except Exception:
            srv.kill()
    (OUT / f"probe_tuples_{name}.json").write_text(json.dumps(
        {"name": name, "gguf": gguf, "prompt": "generate.v1 (request as the only user message)", "seed": SEED,
         "greedy": True, "max_tokens": MAX_TOKENS, "gen_seconds": round(gen_s, 1), "records": recs},
        indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[{name}] {len(recs)} answers in {gen_s:.0f}s")


def score(name: str, served: bool = False) -> None:
    """served=True applies the generation-time typing import fix first and writes probe_tuples_<name>_served.json."""
    path = OUT / f"probe_tuples_{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    by_id = {t["id"]: t for t in TASKS}
    if served:
        from typing_fix import fix_response

        for r in data["records"]:
            r["response"], r["typing_fix_added"] = fix_response(r["response"])
        path = OUT / f"probe_tuples_{name}_served.json"
        data["name"], data["served"] = f"{name}_served", True
    for r in data["records"]:
        code = code_of(r["response"])
        r["score"] = {"outcome": "no_code", "mutated_input": False, "cases": []} if code is None else run(code, by_id[r["id"]])
    data["summary"] = {"outcomes": dict(Counter(r["score"]["outcome"] for r in data["records"])),
                       "mutated_input": sum(r["score"]["mutated_input"] for r in data["records"]),
                       "stopped_on_eos": sum(r["hit_eos"] for r in data["records"]),
                       "typing_fixes": {r["id"]: r["typing_fix_added"] for r in data["records"] if r.get("typing_fix_added")}}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[{name}]", data["summary"])


def table(names: list[str]) -> None:
    runs = {n: json.loads((OUT / f"probe_tuples_{n}.json").read_text(encoding="utf-8")) for n in names}
    rows = ["correct", "tuple_item_assignment", "tuple_other_mutation", "container_type", "wrong_answer", "error",
            "timeout", "no_code"]
    print("| outcome | " + " | ".join(names) + " |\n|---|" + "---|" * len(names))
    for k in rows:
        print(f"| {k} | " + " | ".join(str(r["summary"]["outcomes"].get(k, 0)) for r in runs.values()) + " |")
    print("| mutated the caller's input (any outcome) | " + " | ".join(str(r["summary"]["mutated_input"]) for r in runs.values()) + " |")
    print("| stopped on its own | " + " | ".join(str(r["summary"]["stopped_on_eos"]) for r in runs.values()) + " |")
    if len(names) == 2:
        a, b = ({r["id"]: r["score"]["outcome"] for r in runs[n]["records"]} for n in names)
        print(f"\nper task: both correct {sum(a[i] == b[i] == 'correct' for i in a)}, only {names[0]} {sum(a[i] == 'correct' != b[i] for i in a)}, "
              f"only {names[1]} {sum(b[i] == 'correct' != a[i] for i in a)}")
        for i in a:
            if a[i] != b[i] or a[i] != "correct":
                print(f"  {i:22s} {names[0]}={a[i]:22s} {names[1]}={b[i]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["validate", "gen", "score", "table"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--name")
    ap.add_argument("--gguf")
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--served", action="store_true", help="score with the generation-time typing import fix applied")
    a = ap.parse_args()
    if a.stage == "validate":
        validate()
    elif a.stage == "gen":
        gen(a.name, a.gguf, a.threads, a.parallel)
    elif a.stage == "score":
        score(a.name, a.served)
    else:
        table(a.names)
