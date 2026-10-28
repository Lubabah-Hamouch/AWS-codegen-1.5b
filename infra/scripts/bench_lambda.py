"""Benchmark the deployed model on real Graviton Lambda across memory/thread configurations.

    python bench_lambda.py URL [function-name]

For each (memory MB, llama threads) config: change the function configuration (forces a fresh execution environment),
time a cold /health, run real generations, then read the REPORT lines from CloudWatch for Init Duration, Billed
Duration and Max Memory Used. Results go to docs/bench_lambda_results.json. Leaves the kill switch ON, limits restored.
"""

import json
import re
import statistics as st
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3

URL = sys.argv[1].rstrip("/")
FN = sys.argv[2] if len(sys.argv) > 2 else "codegen-backend"
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "docs" / "bench_lambda_results.json"
S = boto3.Session(profile_name="codegen-spike", region_name="eu-north-1")
LAM, LOGS = S.client("lambda"), S.client("logs")
CONFIGS = [(1536, 1), (2048, 1), (3008, 2)]  # (MB, llama threads): ~0.9, ~1.2, ~1.7 vCPU of Lambda CPU share; account max is 3008 MB
PROMPTS = ["Write a Python function that returns the nth Fibonacci number.",
           "Write a function that checks whether a string is a palindrome, ignoring case and punctuation.",
           "Write a function that merges two sorted lists into one sorted list."]
RUNS = 6


def seed(*a):
    subprocess.run([sys.executable, str(HERE / "seed_state.py"), *a], check=True, capture_output=True)


def gen(prompt, max_tokens=300):
    req = urllib.request.Request(URL + "/generate", data=json.dumps({"prompt": prompt, "max_tokens": max_tokens}).encode(),
                                 headers={"content-type": "application/json"})
    t0, first, name, done = time.monotonic(), None, None, None
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode().strip()
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    if name == "token" and first is None:
                        first = time.monotonic() - t0
                    elif name == "done":
                        done = json.loads(line[5:])
            return {"status": r.status, "client_total_s": round(time.monotonic() - t0, 2),
                    "client_ttft_s": round(first, 2) if first else None, **(done or {})}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode()[:120]}


def health_time():
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(URL + "/health", timeout=120) as r:
            return r.status, round(time.monotonic() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, round(time.monotonic() - t0, 2)


def reports(since_ms):
    time.sleep(12)  # log ingestion delay
    ev, tok = [], None
    while True:
        kw = dict(logGroupName=f"/aws/lambda/{FN}", startTime=since_ms, filterPattern='"REPORT RequestId"')
        if tok:
            kw["nextToken"] = tok
        r = LOGS.filter_log_events(**kw)
        ev += r["events"]
        tok = r.get("nextToken")
        if not tok:
            break
    out = []
    for e in sorted(ev, key=lambda e: e["timestamp"]):
        m = e["message"]
        g = lambda pat: float(re.search(pat, m).group(1)) if re.search(pat, m) else None  # noqa: E731
        out.append({"duration_ms": g(r"\tDuration: ([\d.]+) ms"), "billed_ms": g(r"Billed Duration: ([\d.]+) ms"),
                    "max_mem_mb": g(r"Max Memory Used: ([\d.]+) MB"), "init_ms": g(r"Init Duration: ([\d.]+) ms")})
    return out


base_env = LAM.get_function_configuration(FunctionName=FN)["Environment"]["Variables"]
seed("--set", "global_daily=1000", "anon_ip_daily=1000", "anon_total_daily=1000", "max_concurrency=2")
seed("--kill", "off")
results = []
try:
    for mem, thr in CONFIGS:
        print(f"\n=== {mem} MB, {thr} thread(s)", flush=True)
        since = int(time.time() * 1000)
        LAM.update_function_configuration(FunctionName=FN, MemorySize=mem, Environment={"Variables": {
            **base_env, "LLAMA_THREADS": str(thr), "BENCH_NONCE": str(time.time())}})
        while LAM.get_function_configuration(FunctionName=FN)["LastUpdateStatus"] != "Successful":
            time.sleep(1)
        time.sleep(5)
        since = int(time.time() * 1000)
        hs, cold_health = health_time()
        print(f"cold /health: status={hs} {cold_health}s", flush=True)
        runs = [gen(PROMPTS[i % 3]) for i in range(RUNS)]
        for r in runs:
            print("  ", {k: r.get(k) for k in ("status", "tokens", "ttft_s", "client_ttft_s", "tok_s", "client_total_s", "finish_reason")}, flush=True)
        results.append({"memory_mb": mem, "threads": thr, "cold_health_s": cold_health, "runs": runs, "_since": since})

    for res in results:
        rep = reports(res["_since"])
        res["reports"] = rep
        res.pop("_since")
        cold, gens = rep[0], rep[1:1 + RUNS]
        ok = [r for r in res["runs"] if r.get("status") == 200]
        res["summary"] = {
            "init_ms": cold["init_ms"], "cold_health_billed_ms": cold["billed_ms"], "idle_mem_mb": cold["max_mem_mb"],
            "peak_mem_mb": max(g["max_mem_mb"] for g in gens) if gens else None,
            "tok_s_median": st.median(r["tok_s"] for r in ok if r.get("tok_s")),
            "server_ttft_s_median": st.median(r["ttft_s"] for r in ok if r.get("ttft_s")),
            "first_gen_ttft_s": ok[0].get("ttft_s"), "tokens_mean": round(st.mean(r["tokens"] for r in ok), 1),
            "billed_s_per_generation": round(st.mean(g["billed_ms"] for g in gens) / 1000, 2),
        }
        res["summary"]["gb_s_per_generation"] = round(res["memory_mb"] / 1024 * res["summary"]["billed_s_per_generation"], 2)
        print(res["memory_mb"], json.dumps(res["summary"]))
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("\nwrote", OUT)
finally:
    seed("--set", "global_daily=100", "anon_ip_daily=5", "anon_total_daily=50", "max_concurrency=2")
    seed("--kill", "on")
    print("kill switch ON, limits restored")
