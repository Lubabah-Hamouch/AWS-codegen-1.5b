"""Live guardrail + SSE tests against the deployed Spike 1 Function URL.

    python live_tests.py URL

Leaves the kill switch OFF and limits restored only if every step ran; always prints a final state summary.
"""

import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3

URL = sys.argv[1].rstrip("/")
HERE = Path(__file__).resolve().parent
KEY = (HERE.parent / ".demo-key").read_text(encoding="utf-8").strip()
SESSION = boto3.Session(profile_name="codegen-spike", region_name="eu-north-1")
DB, LAM = SESSION.client("dynamodb"), SESSION.client("lambda")
TABLE = "codegen-state"
results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def seed(*args: str) -> None:
    subprocess.run([sys.executable, str(HERE / "seed_state.py"), *args], check=True, capture_output=True)


def call(path: str, key: str | None = None, read_timeout: int = 60):
    """Return (status, body_text, event_times) where event_times are seconds-from-request for each SSE data line."""
    req = urllib.request.Request(URL + path, headers={"x-api-key": key} if key else {})
    t0, times = time.monotonic(), []
    try:
        with urllib.request.urlopen(req, timeout=read_timeout) as r:
            body = []
            for raw in r:
                line = raw.decode()
                body.append(line)
                if line.startswith("data:"):
                    times.append(round(time.monotonic() - t0, 2))
            return r.status, "".join(body), times
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), times


def global_count() -> int:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    it = DB.get_item(TableName=TABLE, Key={"pk": {"S": f"day#{day}#global"}}, ConsistentRead=True).get("Item")
    return int(it["n"]["N"]) if it else 0


def clear_counters() -> None:
    for page in DB.get_paginator("scan").paginate(TableName=TABLE, ProjectionExpression="pk"):
        for it in page["Items"]:
            if it["pk"]["S"].startswith(("day#", "slot#")):
                DB.delete_item(TableName=TABLE, Key={"pk": it["pk"]})


fn = LAM.get_function_configuration(FunctionName="codegen-spike")
check("function is arm64 container image", fn["Architectures"] == ["arm64"] and fn["PackageType"] == "Image",
      f"arch={fn['Architectures']} package={fn['PackageType']} memory={fn['MemorySize']}MB timeout={fn['Timeout']}s")
clear_counters()
seed("--set", "global_daily=100", "max_concurrency=2", "anon_ip_daily=5", "anon_total_daily=50")

# 1. kill switch ON (the deployed state): refuse everything guarded, health stays reachable
seed("--kill", "on")
s, b, _ = call("/hello?n=3")
check("kill switch ON -> 503, no work done", s == 503 and "disabled" in b, f"status={s} body={b.strip()[:60]}")
check("kill switch ON leaves /health reachable (readiness only)", call("/health")[0] == 200)

# 2. kill switch OFF: stream, and measure whether events arrive incrementally (first request = cold start)
seed("--kill", "off")
t0 = time.monotonic()
s, b, times = call("/hello?n=15&delay=0.4")
total = time.monotonic() - t0
spread = times[-1] - times[0] if len(times) > 1 else 0
check("SSE stream through real Function URL", s == 200 and len(times) == 16 and "event: done" in b,
      f"status={s} data_lines={len(times)} (15 events + the final done event) first_event={times[0] if times else None}s last_event={times[-1] if times else None}s total={total:.1f}s")
check("events arrive incrementally (not buffered to the end)", spread > 4.5,
      f"spread between first and last event = {spread:.2f}s (expected ~5.6s); first 5 arrivals {times[:5]}")
s2, _, t2 = call("/hello?n=3&delay=0.1")
check("warm request first event latency", s2 == 200, f"first_event={t2[0] if t2 else None}s (cold was {times[0] if times else None}s)")

# 3. api keys
s, b, _ = call("/hello?n=1", key=KEY)
check("valid demo key accepted", s == 200 and "key#demo" in b, f"status={s}")
s, b, _ = call("/hello?n=1", key="not-a-real-key")
check("invalid key -> 401", s == 401, f"status={s}")

# 4. anonymous per-IP daily cap (this machine's IP). One anonymous request already used in step 2 (+1 warm = 2).
used = 2
codes = []
for _ in range(6):
    codes.append(call("/hello?n=1")[0])
ok_n = codes.count(200)
check("anonymous per-IP cap enforced (limit 5/day)", ok_n == 5 - used and codes[ok_n:] and all(c == 429 for c in codes[ok_n:]),
      f"already used {used}; next 6 statuses = {codes}")

# 5. concurrency cap: demo key (not IP-limited), 3 parallel long streams, max_concurrency=2
out = {}


def long_call(i):
    out[i] = call("/hello?n=14&delay=0.5", key=KEY)[:2]


ts = [threading.Thread(target=long_call, args=(i,)) for i in range(3)]
[t.start() or time.sleep(0.4) for t in ts]
[t.join() for t in ts]
sts = sorted(v[0] for v in out.values())
check("concurrency cap: 2 of 3 parallel streams admitted, 1 rejected 429 busy", sts == [200, 200, 429],
      f"statuses={sts}")
time.sleep(1)
check("slots released afterwards", call("/hello?n=1", key=KEY)[0] == 200)

# 6. global daily cap
cur = global_count()
seed("--set", f"global_daily={cur + 1}")
s_a = call("/hello?n=1", key=KEY)
s_b = call("/hello?n=1", key=KEY)
check("global daily cap: next request passes, the one after is refused", s_a[0] == 200 and s_b[0] == 429 and "capacity" in s_b[1],
      f"count was {cur}; statuses {s_a[0]}, {s_b[0]} body={s_b[1].strip()[:50]}")
seed("--set", "global_daily=100")

# 7. out-of-band kill: Function URL auth -> AWS_IAM; AWS rejects before any code runs. The change takes a few seconds
# to propagate (status can flap while it does), so poll until two consecutive probes agree.
def settle(want: int, limit_s: int = 120):
    t0, last, hist = time.time(), None, []
    while time.time() - t0 < limit_s:
        c = call("/health")[0]
        hist.append((round(time.time() - t0, 1), c))
        if c == want and last == want:
            return round(time.time() - t0, 1), hist
        last = c
        time.sleep(1.5)
    return None, hist


LAM.update_function_url_config(FunctionName="codegen-spike", AuthType="AWS_IAM")
took, hist = settle(403)
check("out-of-band kill (URL auth=AWS_IAM) -> 403 from AWS, code never reached", took is not None,
      f"stable after {took}s; probes {hist}")
LAM.update_function_url_config(FunctionName="codegen-spike", AuthType="NONE")
took, hist = settle(200)
check("out-of-band kill reversed -> serving again", took is not None, f"stable after {took}s; probes {hist}")

clear_counters()
print("\nSUMMARY:", sum(r[1] for r in results), "/", len(results), "passed")
for n, ok, d in results:
    if not ok:
        print("FAILED:", n, d)
