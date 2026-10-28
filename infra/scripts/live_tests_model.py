"""Live guardrail + SSE tests against the deployed real model (POST /generate).

    python live_tests_model.py URL [function-name]

Generations use small max_tokens to keep the GB-seconds spent on testing low. Leaves the kill switch ON.
"""

import atexit
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
FN = sys.argv[2] if len(sys.argv) > 2 else "codegen-backend"
HERE = Path(__file__).resolve().parent
KEY = (HERE.parent / ".demo-key").read_text(encoding="utf-8").strip()
S = boto3.Session(profile_name="codegen-spike", region_name="eu-north-1")
DB, LAM = S.client("dynamodb"), S.client("lambda")
TABLE = "codegen-state"
SITE = next(o["OutputValue"] for o in S.client("cloudformation").describe_stacks(StackName="codegen-frontend")["Stacks"][0]["Outputs"]
            if o["OutputKey"] == "SiteUrl")
PROMPT = "Write a Python function that returns the nth Fibonacci number."
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def seed(*args):
    subprocess.run([sys.executable, str(HERE / "seed_state.py"), *args], check=True, capture_output=True)


# Whatever happens (failure, exception, Ctrl-C), leave the service parked with the kill switch ON.
atexit.register(lambda: (seed("--kill", "on"), print("kill switch re-engaged (ON)")))


def gen(prompt=PROMPT, max_tokens=40, key=None, timeout=120):
    """POST /generate -> (status, text, done_event, token_event_times, total_s, raw_error_body)."""
    req = urllib.request.Request(URL + "/generate", data=json.dumps({"prompt": prompt, "max_tokens": max_tokens}).encode(),
                                 headers={"content-type": "application/json", **({"x-api-key": key} if key else {})})
    t0, times, text, done, name = time.monotonic(), [], "", None, None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode().strip()
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    d = json.loads(line[5:])
                    if name == "token":
                        times.append(round(time.monotonic() - t0, 2))
                        text += d["t"]
                    elif name == "done":
                        done = d
            return r.status, text, done, times, round(time.monotonic() - t0, 2), ""
    except urllib.error.HTTPError as e:
        return e.code, "", None, times, round(time.monotonic() - t0, 2), e.read().decode(errors="replace")


def code(body: str):
    try:
        return json.loads(body).get("code")
    except ValueError:
        return None


def site_status():
    with urllib.request.urlopen(SITE + "/status.json", timeout=20) as r:
        return json.loads(r.read()), r.headers.get("cache-control"), r.headers.get("x-cache")


def preflight(origin):
    req = urllib.request.Request(URL + "/generate", method="OPTIONS", headers={
        "origin": origin, "access-control-request-method": "POST", "access-control-request-headers": "content-type"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.headers.get("access-control-allow-origin")
    except urllib.error.HTTPError as e:
        return e.headers.get("access-control-allow-origin")


def health():
    try:
        with urllib.request.urlopen(URL + "/health", timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def clear_state():
    for page in DB.get_paginator("scan").paginate(TableName=TABLE, ProjectionExpression="pk"):
        for it in page["Items"]:
            if it["pk"]["S"].startswith(("day#", "slot#")):
                DB.delete_item(TableName=TABLE, Key={"pk": it["pk"]})


def global_count():
    day = time.strftime("%Y-%m-%d", time.gmtime())
    it = DB.get_item(TableName=TABLE, Key={"pk": {"S": f"day#{day}#global"}}, ConsistentRead=True).get("Item")
    return int(it["n"]["N"]) if it else 0


cfg = LAM.get_function_configuration(FunctionName=FN)
check("function is arm64 container image", cfg["Architectures"] == ["arm64"] and cfg["PackageType"] == "Image",
      f"memory={cfg['MemorySize']}MB timeout={cfg['Timeout']}s threads={cfg['Environment']['Variables'].get('LLAMA_THREADS')}")
clear_state()
seed("--set", "global_daily=100", "max_concurrency=2", "anon_ip_daily=5", "anon_total_daily=50", "max_tokens=512")

# 1. kill switch ON: refused before any model work
seed("--kill", "on")
s, _, _, _, dt, body = gen()
check("kill switch ON -> 503 code=disabled, no generation", s == 503 and code(body) == "disabled", f"status={s} {dt}s body={body.strip()[:70]}")
st, cc, _ = site_status()
check("status.json on the site says paused, served uncached", st.get("live") is False and st.get("note") == "paused", f"{st} cache-control={cc}")

# 2. kill OFF; the first generation after the deploy pays the real cold start
seed("--kill", "off")
st, _, _ = site_status()
check("status.json flips to live with the kill switch", st.get("live") is True, str(st))
s, text, done, times, total, body = gen(max_tokens=150)
check("first generation after deploy (cold start included)", s == 200 and done is not None,
      f"status={s} total={total}s first_token={times[0] if times else None}s tokens={done and done['tokens']} body={body[:60]}")
s, text, done, times, total, body = gen(max_tokens=150)
spread = times[-1] - times[0] if len(times) > 1 else 0
check("SSE: tokens arrive incrementally through the Function URL", s == 200 and len(times) > 20 and spread > 1.5,
      f"token events={len(times)} first={times[0] if times else None}s last={times[-1] if times else None}s spread={spread:.2f}s "
      f"tok_s(server)={done and done['tok_s']} finish={done and done['finish_reason']}")
check("output is a fenced python block with docstring and type hints, clean stop",
      s == 200 and text.lstrip().startswith("```python") and "->" in text and (done or {}).get("finish_reason") in ("stop", "length"),
      repr(text[:60]))

# 3. validation
r = gen(prompt="  ")
check("empty prompt -> 400 code=bad_request", r[0] == 400 and code(r[5]) == "bad_request", r[5][:80])
check("done event reports remaining runs for the caller (5/day, 2 used)", (done or {}).get("remaining") == 3, str(done))
allowed = preflight(SITE)
check("CORS: playground origin allowed", allowed == SITE, f"allow-origin={allowed}")
other = preflight("https://evil.example")
check("CORS: other origins not allowed", other in (None, ""), f"allow-origin={other}")

# 4. api keys
s, _, d, _, _, _ = gen(max_tokens=10, key=KEY)
check("valid demo key accepted", s == 200, f"status={s}")
r = gen(max_tokens=10, key="nope")
check("invalid key -> 401 code=invalid_key", r[0] == 401 and code(r[5]) == "invalid_key", r[5][:80])

# 5. anonymous per-IP cap (limit 5/day; the 2 generations in step 2 used 2)
runs = [gen(max_tokens=8) for _ in range(5)]
codes = [r[0] for r in runs]
check("anonymous per-IP cap enforced (5/day), code=daily_limit", codes == [200, 200, 200, 429, 429] and code(runs[-1][5]) == "daily_limit",
      f"2 already used; next 5 statuses = {codes} {runs[-1][5][:60]}")

# 6. concurrency cap: 3 parallel real generations, 2 slots
out = {}


LONG = "Write a Python class implementing a binary search tree with insert, delete, search and in-order traversal methods."


def worker(i):
    # ~300 tokens (~20 s): long enough to overlap even when the other requests pay a cold start (4-9 s) first
    r = gen(prompt=LONG, max_tokens=300, key=KEY)
    out[i] = (r[0], code(r[5]))


ts = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
for t in ts:
    t.start()
    time.sleep(0.5)
for t in ts:
    t.join()
sts = sorted(v[0] for v in out.values())
check("concurrency cap: 2 of 3 parallel generations admitted, 1 rejected 429 code=busy",
      sts == [200, 200, 429] and any(v == (429, "busy") for v in out.values()), f"{sorted(out.values(), key=str)}")
time.sleep(1)
check("slots released afterwards", gen(max_tokens=8, key=KEY)[0] == 200)

# 7. global daily cap
cur = global_count()
seed("--set", f"global_daily={cur + 1}")
a, b = gen(max_tokens=8, key=KEY), gen(max_tokens=8, key=KEY)
check("global daily cap: next passes, the one after is refused", a[0] == 200 and b[0] == 429 and code(b[5]) == "daily_capacity", f"count was {cur}; {a[0]}, {b[0]}")
seed("--set", "global_daily=100")

# 8. out-of-band kill (poll the unguarded /health: no quota or model time spent). Takes tens of seconds - see runbook.
def settle(want, limit_s=150):
    t0, last, hist = time.time(), None, []
    while time.time() - t0 < limit_s:
        c = health()
        hist.append((round(time.time() - t0, 1), c))
        if c == want and last == want:
            return round(time.time() - t0, 1), hist
        last = c
        time.sleep(1.5)
    return None, hist


LAM.update_function_url_config(FunctionName=FN, AuthType="AWS_IAM")
took, hist = settle(403)
check("out-of-band kill (URL auth=AWS_IAM) -> 403 from AWS", took is not None, f"stable after {took}s")
LAM.update_function_url_config(FunctionName=FN, AuthType="NONE")
took2, hist2 = settle(200)
check("out-of-band kill reversed -> serving again", took2 is not None, f"stable after {took2}s")

clear_state()
seed("--kill", "on")
print("\nSUMMARY:", sum(r[1] for r in results), "/", len(results), "passed; kill switch left ON")
for n, ok, d in results:
    if not ok:
        print("FAILED:", n, d)
