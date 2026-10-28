"""Live guardrail tests that keep the Function URL locked (AWS_IAM) the whole time: the public gets 403 throughout.
The requests here are SigV4-signed with the operator's credentials, which AWS lets through to the app.

    python live_tests_private.py              per-IP cap, concurrency cap, global cap, app kill switch
    python live_tests_private.py --breaker    ... then trips the circuit breaker with real traffic

Quota part: temporary limits and 8-48 token generations (well under 100 GB-s, inside the free tier). The app kill flag
is opened with --no-status, so status.json keeps saying "paused" and the site never offers live runs.
--breaker: ~750 signed GET /health (each a few ms) inside one 5-minute alarm period, then waits for the real alarm ->
SNS -> breaker -> both layers. The breaker writes status.json "circuit breaker" itself; it is set back to "paused"
on exit. Exit always restores the default limits and the kill switch ON. Today's counters are cleared (parked: no
visitors use them).
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
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

FN, REGION, TABLE = "codegen-backend", "eu-north-1", "codegen-state"
HERE = Path(__file__).resolve().parent
S = boto3.Session(profile_name="codegen-spike", region_name=REGION)
DB, LAM, CW = S.client("dynamodb"), S.client("lambda"), S.client("cloudwatch")
URL = LAM.get_function_url_config(FunctionName=FN)["FunctionUrl"].rstrip("/")
CREDS = S.get_credentials().get_frozen_credentials()
DEFAULTS = ["anon_ip_daily=5", "anon_total_daily=50", "global_daily=100", "max_concurrency=2"]
PROMPT = "Write a Python function that returns the nth Fibonacci number."
results = []


def check(name, ok, detail=""):
    ok = bool(ok)
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def seed(*a):
    subprocess.run([sys.executable, str(HERE / "seed_state.py"), *a], check=True, capture_output=True)


def restore():
    seed("--set", *DEFAULTS)
    seed("--kill", "on")  # also writes status.json "paused", replacing anything the breaker wrote
    print("restored: default limits, kill switch ON, status.json paused", flush=True)


def call(method, path, body=None, signed=True, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"content-type": "application/json"} if data else {}
    if signed:
        req = AWSRequest(method=method, url=URL + path, data=data, headers=headers)
        SigV4Auth(CREDS, "lambda", REGION).add_auth(req)
        headers = dict(req.headers)
    r = urllib.request.Request(URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read().decode(errors="replace"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace"), dict(e.headers)


def gen(max_tokens=8):
    return call("POST", "/generate", {"prompt": PROMPT, "max_tokens": max_tokens})


def code(body):
    try:
        return json.loads(body).get("code")
    except ValueError:
        return None


def clear():
    for it in DB.scan(TableName=TABLE, ProjectionExpression="pk")["Items"]:
        if it["pk"]["S"].startswith(("day#", "slot#")):
            DB.delete_item(TableName=TABLE, Key={"pk": it["pk"]})


def auth():
    return LAM.get_function_url_config(FunctionName=FN)["AuthType"]


def site_status():
    bucket = next(o["OutputValue"] for o in S.client("cloudformation").describe_stacks(StackName="codegen-frontend")
                  ["Stacks"][0]["Outputs"] if o["OutputKey"] == "BucketName")
    return json.loads(S.client("s3").get_object(Bucket=bucket, Key="status.json")["Body"].read())


# ---- preconditions: locked URL, public refused ----
if auth() != "AWS_IAM":
    sys.exit("Function URL is not AWS_IAM: refusing to run (this suite must never open the URL)")
check("public (unsigned) request refused by AWS before any code runs", call("GET", "/health", signed=False)[0] == 403)
atexit.register(restore)

# ---- quota part ----
seed("--set", "anon_ip_daily=2", "anon_total_daily=50", "global_daily=100", "max_concurrency=2")
clear()
seed("--kill", "off", "--no-status")
check("status.json still says paused with the app flag open", site_status().get("live") is False, str(site_status()))
t0 = time.time()
while True:
    s, b, _ = call("GET", "/health", timeout=150)
    if s == 200 or time.time() - t0 > 150:
        break
    time.sleep(3)
check("signed request reaches the app; model ready", s == 200, f"{b.strip()} after {time.time() - t0:.1f}s")

runs = [gen() for _ in range(3)]
st = [r[0] for r in runs]
check("per-IP cap (temporarily 2/day): 200, 200, then 429 code=daily_limit with retry-after",
      st == [200, 200, 429] and code(runs[2][1]) == "daily_limit" and "retry-after" in {k.lower() for k in runs[2][2]},
      f"statuses={st} body={runs[2][1].strip()[:80]}")

seed("--set", "anon_ip_daily=10")
clear()
par = [None] * 3


def worker(i):
    # Long enough (~8 s) to outlast a cold start: requests that land on new instances wait ~3.5-4.5 s for init, and
    # with short generations the first one released its slot before they were admitted (no real overlap).
    par[i] = gen(max_tokens=160)


ths = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
[t.start() for t in ths]
[t.join() for t in ths]
st = sorted(p[0] for p in par)
busy = [p for p in par if p[0] == 429]
check("concurrency cap: 3 parallel generations -> 2 admitted, 1 refused code=busy",
      st == [200, 200, 429] and busy and code(busy[0][1]) == "busy", f"statuses={st}")
check("slots released afterwards", gen()[0] == 200)

clear()
seed("--set", "global_daily=1")
a, b = gen(), gen()
check("global cap (temporarily 1/day): next passes, the one after is refused code=daily_capacity",
      a[0] == 200 and b[0] == 429 and code(b[1]) == "daily_capacity", f"{a[0]}, {b[0]} {b[1].strip()[:80]}")

seed("--set", *DEFAULTS)
seed("--kill", "on", "--no-status")
s, b, _ = gen()
check("app kill switch ON -> 503 code=disabled, no generation", s == 503 and code(b) == "disabled", f"{s} {b.strip()[:60]}")

# ---- breaker part: real traffic, real alarm ----
if "--breaker" in sys.argv:
    state = CW.describe_alarms(AlarmNames=["codegen-backend-invocation-flood"])["MetricAlarms"][0]["StateValue"]
    check("alarm starts in OK (the breaker acts on the transition into ALARM)", state == "OK", state)
    # Land the whole flood inside one 5-minute period (the alarm sums Invocations per aligned 300 s period).
    wait = (300 - time.time() % 300) + 3
    print(f"waiting {wait:.0f}s for the start of a 5-minute period", flush=True)
    time.sleep(wait)
    N, counts, lock, nxt = 750, {}, threading.Lock(), [0]

    def flood():
        while True:
            with lock:
                if nxt[0] >= N:
                    return
                nxt[0] += 1
            s = call("GET", "/health", timeout=30)[0]
            with lock:
                counts[s] = counts.get(s, 0) + 1

    t0 = time.time()
    ths = [threading.Thread(target=flood) for _ in range(6)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    sent = time.time() - t0
    check(f"flood: {N} signed GET /health in one period", counts.get(200, 0) > 600,
          f"statuses={counts} in {sent:.0f}s ({time.strftime('%H:%M:%S', time.gmtime(t0))}Z start)")
    t1, state = time.time(), None
    while time.time() - t1 < 900:
        state = CW.describe_alarms(AlarmNames=["codegen-backend-invocation-flood"])["MetricAlarms"][0]["StateValue"]
        if state == "ALARM":
            break
        time.sleep(20)
    check("real traffic -> alarm goes to ALARM", state == "ALARM", f"after {time.time() - t1:.0f}s from end of flood")
    t2, flag = time.time(), {}
    while time.time() - t2 < 120:
        flag = DB.get_item(TableName=TABLE, Key={"pk": {"S": "config#killswitch"}}, ConsistentRead=True)["Item"]
        if flag.get("reason", {}).get("S", "").startswith("circuit breaker"):
            break
        time.sleep(5)
    check("breaker: app kill switch set by the breaker", flag.get("reason", {}).get("S", "").startswith("circuit breaker"),
          f"{flag.get('reason', {}).get('S')} ({time.time() - t2:.0f}s after ALARM)")
    check("breaker: Function URL auth AWS_IAM", auth() == "AWS_IAM")
    st = site_status()
    check("breaker: status.json says paused by circuit breaker", st.get("live") is False and st.get("note") == "circuit breaker", str(st))

check("public (unsigned) request still refused at the end", call("GET", "/health", signed=False)[0] == 403)
print(f"\n{sum(ok for _, ok in results)}/{len(results)} passed", flush=True)
sys.exit(0 if all(ok for _, ok in results) else 1)
