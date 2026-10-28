"""Live tests for the Phase 4 hardening: client-IP spoofing, the daily warm-up schedule, and the circuit breaker.

    python live_tests_hardening.py URL

Generations use max_tokens=1. Leaves the kill switch ON and the Function URL auth back at NONE.
"""

import atexit
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3

URL = sys.argv[1].rstrip("/")
FN = "codegen-backend"
HERE = Path(__file__).resolve().parent
S = boto3.Session(profile_name="codegen-spike", region_name="eu-north-1")
DB, LAM, CW, EV = S.client("dynamodb"), S.client("lambda"), S.client("cloudwatch"), S.client("events")
TABLE = "codegen-state"
results = []


def seed(*a):
    subprocess.run([sys.executable, str(HERE / "seed_state.py"), *a], check=True, capture_output=True)


atexit.register(lambda: (seed("--set", "anon_ip_daily=5", "anon_total_daily=50", "global_daily=100"),
                         seed("--kill", "on"), print("kill switch ON, limits restored")))


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)


def clear():
    for it in DB.scan(TableName=TABLE, ProjectionExpression="pk")["Items"]:
        if it["pk"]["S"].startswith(("day#", "slot#")):
            DB.delete_item(TableName=TABLE, Key={"pk": it["pk"]})


def gen(headers=None):
    req = urllib.request.Request(URL + "/generate", data=json.dumps({"prompt": "Write a function that returns 1.", "max_tokens": 1}).encode(),
                                 headers={"content-type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def health():
    try:
        with urllib.request.urlopen(URL + "/health", timeout=120) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def settle(want, limit_s=180):
    t0, last = time.time(), None
    while time.time() - t0 < limit_s:
        c = health()
        if c == want and last == want:
            return round(time.time() - t0, 1)
        last = c
        time.sleep(2)
    return None


# 1. client IP cannot be forged
clear()
seed("--set", "anon_ip_daily=1", "anon_total_daily=50", "global_daily=100")
seed("--kill", "off")
codes = {"first (real IP)": gen(), "second (real IP, cap=1)": gen(),
         "forged x-forwarded-for": gen({"x-forwarded-for": "203.0.113.7"}),
         "forged x-forwarded-for, 2 values": gen({"x-forwarded-for": "198.51.100.1, 198.51.100.2"}),
         "forged x-amzn-request-context": gen({"x-amzn-request-context": json.dumps({"http": {"sourceIp": "192.0.2.55"}})})}
ip_buckets = [i["pk"]["S"] for i in DB.scan(TableName=TABLE)["Items"] if "#ip#" in i["pk"]["S"]]
check("per-IP cap: forged headers land in the real IP's bucket (all refused)",
      list(codes.values()) == [200, 429, 429, 429, 429] and len(ip_buckets) == 1, f"{codes}; ip buckets={len(ip_buckets)}")
clear()
seed("--kill", "on")

# 2. daily warm-up schedule
rules = EV.list_rule_names_by_target(TargetArn=LAM.get_function(FunctionName=FN)["Configuration"]["FunctionArn"])["RuleNames"]
rule = EV.describe_rule(Name=rules[0]) if rules else {}
check("daily warm-up rule exists, enabled, rate(1 day)", rule.get("State") == "ENABLED" and rule.get("ScheduleExpression") == "rate(1 day)",
      f"{rules} {rule.get('ScheduleExpression')} {rule.get('State')}")
inv = LAM.invoke(FunctionName=FN, Payload=json.dumps({"source": "codegen.daily-warmup"}).encode())
payload = inv["Payload"].read().decode()
check("warm-up event invokes cleanly while the kill switch is ON", inv["StatusCode"] == 200 and "FunctionError" not in inv and '"warm": true' in payload,
      f"status={inv['StatusCode']} payload={payload[:120]}")

# 3. circuit breaker: drive the real alarm into ALARM -> SNS -> breaker Lambda -> both layers
seed("--kill", "off")
assert LAM.get_function_url_config(FunctionName=FN)["AuthType"] == "NONE"
CW.set_alarm_state(AlarmName="codegen-backend-invocation-flood", StateValue="ALARM", StateReason="live test of the circuit breaker")
t0 = time.time()
flag = {}
while time.time() - t0 < 90:
    flag = DB.get_item(TableName=TABLE, Key={"pk": {"S": "config#killswitch"}}, ConsistentRead=True).get("Item", {})
    if flag.get("enabled", {}).get("BOOL") and flag.get("reason", {}).get("S", "").startswith("circuit breaker"):
        break
    time.sleep(2)
auth = LAM.get_function_url_config(FunctionName=FN)["AuthType"]
check("breaker: alarm -> app kill switch ON", flag.get("reason", {}).get("S", "").startswith("circuit breaker"),
      f"after {time.time() - t0:.0f}s reason={flag.get('reason', {}).get('S')}")
check("breaker: alarm -> Function URL auth AWS_IAM", auth == "AWS_IAM", f"auth={auth}")
took = settle(403)
check("breaker: requests now refused by AWS (403) before invoking", took is not None, f"stable after {took}s")
site = next(o["OutputValue"] for o in S.client("cloudformation").describe_stacks(StackName="codegen-frontend")["Stacks"][0]["Outputs"]
            if o["OutputKey"] == "SiteUrl")
with urllib.request.urlopen(site + "/status.json", timeout=20) as r:
    st = json.loads(r.read())
check("breaker: site status.json says paused by circuit breaker", st.get("live") is False and st.get("note") == "circuit breaker", str(st))

# restore: URL auth back to NONE (kill switch stays ON), alarm back to OK
LAM.update_function_url_config(FunctionName=FN, AuthType="NONE")
CW.set_alarm_state(AlarmName="codegen-backend-invocation-flood", StateValue="OK", StateReason="live test finished")
took = settle(200)
check("restored: URL auth NONE, /health reachable again", took is not None, f"stable after {took}s")

print("\nSUMMARY:", sum(ok for _, ok in results), "/", len(results), "passed")
