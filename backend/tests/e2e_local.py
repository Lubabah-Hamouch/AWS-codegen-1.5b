"""Local end-to-end check of the real app: container (x86 build of the same Dockerfile) + DynamoDB Local.

    docker run -d --name ddb-local -p 8000:8000 amazon/dynamodb-local
    python backend/tests/e2e_local.py IMAGE          (IMAGE needs python3.12 + boto3; app dir is bind-mounted)

Checks the request/response contract, SSE framing, input validation, the kill switch and the concurrency cap
with a real model. Functional only: timings here say nothing about Lambda.
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

IMAGE = sys.argv[1]
APP = str(Path(__file__).resolve().parents[1] / "app")
PORT, NAME = 9300, "e2e-local"
ENV = dict(AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x", AWS_REGION="eu-north-1", AWS_DEFAULT_REGION="eu-north-1")
db = boto3.client("dynamodb", endpoint_url="http://localhost:8000", region_name="eu-north-1", aws_access_key_id="x", aws_secret_access_key="x")
fails = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}", flush=True)
    if not ok:
        fails.append(name)


def put(pk, **attrs):
    item = {"pk": {"S": pk}}
    for k, v in attrs.items():
        item[k] = {"BOOL": v} if isinstance(v, bool) else {"N": str(v)}
    db.put_item(TableName="e2e-state", Item=item)


def post(body, key=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/generate", data=data,
                                 headers={"content-type": "application/json", **({"x-api-key": key} if key else {})})
    t0, events, ttft = time.monotonic(), [], None
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            name = None
            for line in r:
                line = line.decode().strip()
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    ttft = ttft or time.monotonic() - t0
                    events.append((name, json.loads(line[5:])))
            return r.status, events, ttft
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), None


subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
try:
    db.delete_table(TableName="e2e-state")
except Exception:
    pass
db.create_table(TableName="e2e-state", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
put("config#global", max_concurrency=1, global_daily=1000, anon_ip_daily=1000, anon_total_daily=1000, max_tokens=300)
put("config#killswitch", enabled=False)

envargs = [x for k, v in {**ENV, "TABLE_NAME": "e2e-state", "DDB_ENDPOINT": "http://host.docker.internal:8000",
                          "LLAMA_THREADS": "2"}.items() for x in ("-e", f"{k}={v}")]
subprocess.run(["docker", "run", "-d", "--name", NAME, "--cpus", "2", "--memory", "3g", "-p", f"{PORT}:8080", "-v", f"{APP}:/app:ro",
                *envargs, IMAGE], check=True, capture_output=True)
try:
    t0 = time.time()
    while time.time() - t0 < 180:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    check("model loads and /health turns 200", time.time() - t0 < 180, f"{time.time() - t0:.1f}s")

    s, ev, ttft = post({"prompt": "Write a Python function that returns the nth Fibonacci number."})
    text = "".join(d["t"] for n, d in ev if n == "token")
    done = [d for n, d in ev if n == "done"]
    check("200 + token events + one done event", s == 200 and len(done) == 1 and len(ev) > 20, f"events={len(ev)} ttft={ttft and round(ttft, 2)}s")
    check("output is one fenced python block with docstring and type hints",
          text.count("```") == 2 and text.lstrip().startswith("```python") and '"""' in text and "->" in text, repr(text[:70]))
    check("done event carries finish_reason, token counts, tok/s, prompt version",
          done and done[0]["finish_reason"] == "stop" and done[0]["tokens"] and done[0]["tok_s"] and done[0]["prompt_version"] == "generate.v1", str(done[0]) if done else "")

    s, ev, _ = post({"prompt": "Write a function that adds two numbers.", "max_tokens": 5})
    done = [d for n, d in ev if n == "done"]
    check("max_tokens is honoured", s == 200 and done and done[0]["finish_reason"] == "length" and done[0]["tokens"] <= 5, str(done[0] if done else ev))
    s, ev, _ = post({"prompt": "Write a Python function that sorts a list.", "max_tokens": 99999})
    done = [d for n, d in ev if n == "done"]
    check("max_tokens is capped by the server (300)", s == 200 and done and done[0]["tokens"] <= 300, str(done[0] if done else ev))

    check("empty prompt -> 400", post({"prompt": "  "})[0] == 400)
    check("non-string prompt -> 400", post({"prompt": 5})[0] == 400)
    check("oversized prompt -> 400", post({"prompt": "x" * 2001})[0] == 400)
    check("bad json -> 400", post(None, raw=b"{nope")[0] == 400)
    check("bad max_tokens -> 400", post({"prompt": "hi", "max_tokens": 0})[0] == 400)
    check("oversized body -> 413", post(None, raw=b"{" + b" " * 9000 + b"}")[0] == 413)

    # concurrency cap (1 slot): a second request while the first streams is rejected, then admitted after it ends
    res = {}
    t = threading.Thread(target=lambda: res.update(first=post({"prompt": "Write a Python function that checks if a number is prime.", "max_tokens": 200})))
    t.start()
    time.sleep(1.5)
    s2 = post({"prompt": "Write a Python function that reverses a string."})[0]
    t.join()
    check("second request during a stream -> 429 busy, first one finishes", s2 == 429 and res["first"][0] == 200, f"second={s2} first={res['first'][0]}")
    check("slot released afterwards", post({"prompt": "Write a function that returns 1.", "max_tokens": 20})[0] == 200)

    put("config#killswitch", enabled=True)
    s, body, _ = post({"prompt": "Write a function that returns 1."})
    check("kill switch ON -> 503 and nothing generated", s == 503 and body.get("error") == "service disabled", str(body))
    put("config#killswitch", enabled=False)

    # a client that disconnects mid-stream must free the slot and the model
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/generate", data=json.dumps({"prompt": "Write a long Python class implementing a linked list with many methods.", "max_tokens": 300}).encode(), headers={"content-type": "application/json"})
    r = urllib.request.urlopen(req, timeout=60)
    r.readline(); r.readline(); r.close()
    time.sleep(3)
    s, ev, _ = post({"prompt": "Write a function that returns 2.", "max_tokens": 20})
    check("client disconnect mid-stream frees the slot", s == 200, f"next request status={s}")
finally:
    logs = subprocess.run(["docker", "logs", NAME], capture_output=True, text=True)
    print("\n--- app log (done lines)")
    print("\n".join(l for l in (logs.stdout + logs.stderr).splitlines() if "[app" in l and ("done" in l or "error" in l or "away" in l))[:1500])
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
print("\nFAILED:" if fails else "\nALL PASSED", fails if fails else "")
