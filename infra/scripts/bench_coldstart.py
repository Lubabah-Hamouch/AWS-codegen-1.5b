"""Cold starts with the image already cached, plus clean per-config generation cost. One sample =
  1. change an env var (same image digest) -> forces a fresh execution environment, no new image deploy
  2. GET /health, timed end to end (200 only once the model is loaded)       -> cold start
  3. two warm generations                                                     -> tok/s, billed s, memory
  4. CloudWatch REPORT/INIT_REPORT lines for exactly this sample's time window

    python bench_coldstart.py URL [samples_per_config]

The kill switch is turned OFF for the generations and is turned back ON at exit, whatever happens.
Results: docs/bench_coldstart_results.json
"""

import atexit
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
SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 3
FN = "codegen-backend"
HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "docs" / "bench_coldstart_results.json"
CONFIGS = [(1536, 1, ""), (2048, 1, ""), (3008, 2, ""), (3008, 2, "--no-repack")]
PROMPTS = ["Write a Python function that returns the nth Fibonacci number.",
           "Write a function that merges two sorted lists into one sorted list."]
S = boto3.Session(profile_name="codegen-spike", region_name="eu-north-1")
LAM, LOGS = S.client("lambda"), S.client("logs")


def seed(*a):
    subprocess.run([sys.executable, str(HERE / "seed_state.py"), *a], check=True, capture_output=True)


atexit.register(lambda: (seed("--set", "global_daily=100", "anon_ip_daily=5", "anon_total_daily=50"),
                         seed("--kill", "on"), print("kill switch ON, limits restored")))


def health():
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(URL + "/health", timeout=120) as r:
            return r.status, round(time.monotonic() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, round(time.monotonic() - t0, 2)


def gen(prompt):
    req = urllib.request.Request(URL + "/generate", data=json.dumps({"prompt": prompt, "max_tokens": 300}).encode(),
                                 headers={"content-type": "application/json"})
    name, done = None, {}
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            for raw in r:
                line = raw.decode().strip()
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:") and name == "done":
                    done = json.loads(line[5:])
            return {"status": r.status, **done}
    except urllib.error.HTTPError as e:
        return {"status": e.code}


def window(since, until):
    time.sleep(12)
    ev, tok = [], None
    while True:
        kw = dict(logGroupName=f"/aws/lambda/{FN}", startTime=since, endTime=until,
                  filterPattern='?"REPORT RequestId" ?INIT_REPORT')
        if tok:
            kw["nextToken"] = tok
        r = LOGS.filter_log_events(**kw)
        ev += r["events"]
        tok = r.get("nextToken")
        if not tok:
            break
    return [e["message"].strip() for e in sorted(ev, key=lambda e: e["timestamp"])]


def f(pat, s):
    m = re.search(pat, s)
    return float(m.group(1)) if m else None


assert LAM.get_function_url_config(FunctionName=FN)["AuthType"] == "NONE", "URL auth must be NONE"
base = LAM.get_function_configuration(FunctionName=FN)["Environment"]["Variables"]
base.pop("COLD_NONCE", None), base.pop("BENCH_NONCE", None)
seed("--set", "global_daily=1000", "anon_ip_daily=1000", "anon_total_daily=1000", "max_concurrency=2")
seed("--kill", "off")
samples = []
for mem, thr, extra in CONFIGS:
    for i in range(SAMPLES):
        LAM.update_function_configuration(FunctionName=FN, MemorySize=mem, Environment={"Variables": {
            **base, "LLAMA_THREADS": str(thr), "LLAMA_EXTRA": extra, "COLD_NONCE": f"{time.time()}"}})
        while LAM.get_function_configuration(FunctionName=FN)["LastUpdateStatus"] != "Successful":
            time.sleep(1)
        time.sleep(3)
        since = int(time.time() * 1000)
        hs, cold_s = health()
        gens = [gen(p) for p in PROMPTS]
        until = int(time.time() * 1000) + 2000
        lines = window(since, until)
        reports = [l for l in lines if l.startswith("REPORT")]
        s = {"memory_mb": mem, "threads": thr, "extra": extra, "sample": i, "health_status": hs, "cold_health_s": cold_s,
             "init_timeouts": sum("Status: timeout" in l for l in lines),
             "init_ms": f(r"Init Duration: ([\d.]+)", reports[0]) if reports else None,
             "idle_mem_mb": f(r"Max Memory Used: ([\d.]+)", reports[0]) if reports else None,
             "gen": [{"status": g["status"], "tokens": g.get("tokens"), "tok_s": g.get("tok_s"), "ttft_s": g.get("ttft_s"),
                      "billed_ms": f(r"Billed Duration: ([\d.]+)", r), "max_mem_mb": f(r"Max Memory Used: ([\d.]+)", r)}
                     for g, r in zip(gens, reports[1:])],
             "n_reports": len(reports)}
        samples.append(s)
        print(json.dumps(s), flush=True)

OUT.write_text(json.dumps(samples, indent=1), encoding="utf-8")
print("\nper-config summary:")
for mem, thr, extra in CONFIGS:
    ss = [s for s in samples if (s["memory_mb"], s["threads"], s["extra"]) == (mem, thr, extra)]
    g = [x for s in ss for x in s["gen"] if x["status"] == 200 and x["billed_ms"]]
    if not g:
        continue
    billed = st.mean(x["billed_ms"] for x in g) / 1000
    print(json.dumps({"config": f"{mem}MB/{thr}t{(' ' + extra) if extra else ''}",
                      "cold_health_s": [s["cold_health_s"] for s in ss], "init_ms": [s["init_ms"] for s in ss],
                      "init_timeouts": sum(s["init_timeouts"] for s in ss),
                      "idle_mem_mb": [s["idle_mem_mb"] for s in ss], "peak_mem_mb": max(x["max_mem_mb"] for x in g),
                      "tok_s_median": st.median(x["tok_s"] for x in g), "tokens_mean": round(st.mean(x["tokens"] for x in g), 1),
                      "billed_s_per_gen": round(billed, 2), "gb_s_per_gen": round(mem / 1024 * billed, 2)}))
print("wrote", OUT)
