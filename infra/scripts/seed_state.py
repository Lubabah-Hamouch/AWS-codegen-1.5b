"""Seed / adjust guardrail state in the DynamoDB table (idempotent). Secrets never print.

    python seed_state.py --init                  create config#global, config#killswitch (ON), and the demo key
    python seed_state.py --kill on|off           set the DynamoDB kill switch and publish the site's status.json
    python seed_state.py --kill off --no-status  ... but leave status.json alone (private tests with the URL locked)
    python seed_state.py --status                re-publish status.json from the current kill switch
    python seed_state.py --set global_daily=100 anon_ip_daily=5   change limits in config#global
    python seed_state.py --show                  print config (no secrets)

status.json ({"live", "since", "note"}) lives in the codegen-frontend bucket and is served uncached; the playground
reads it on load and shows replays while live is false. The circuit breaker writes the same file.

The demo API key is generated once and written to infra/.demo-key (gitignored); only its SHA-256 is stored.
"""

import argparse
import hashlib
import json
import secrets
import time
from pathlib import Path

import boto3

PROFILE, REGION, TABLE = "codegen-spike", "eu-north-1", "codegen-state"
KEYFILE = Path(__file__).resolve().parents[1] / ".demo-key"
LIMITS = {"global_daily": 100, "max_concurrency": 2, "slot_seconds": 60, "max_tokens": 512,
          "anon_total_daily": 50, "anon_ip_daily": 5}


def write_status(session, live: bool, note: str) -> None:
    try:
        outs = session.client("cloudformation").describe_stacks(StackName="codegen-frontend")["Stacks"][0]["Outputs"]
    except Exception as e:  # frontend not deployed: nothing to publish to
        print("status.json skipped:", type(e).__name__)
        return
    bucket = next(o["OutputValue"] for o in outs if o["OutputKey"] == "BucketName")
    body = {"live": live, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "note": note}
    session.client("s3").put_object(Bucket=bucket, Key="status.json", Body=json.dumps(body).encode(),
                                    ContentType="application/json", CacheControl="no-store")
    print("status.json:", body)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--kill", choices=["on", "off"])
    ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-status", action="store_true")
    a = ap.parse_args()
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    db = session.client("dynamodb")

    if a.init:
        item = {"pk": {"S": "config#global"}, **{k: {"N": str(v)} for k, v in LIMITS.items()}}
        db.put_item(TableName=TABLE, Item=item, ConditionExpression="attribute_not_exists(pk)") if not db.get_item(
            TableName=TABLE, Key={"pk": {"S": "config#global"}}).get("Item") else None
        if not db.get_item(TableName=TABLE, Key={"pk": {"S": "config#killswitch"}}).get("Item"):
            db.put_item(TableName=TABLE, Item={"pk": {"S": "config#killswitch"}, "enabled": {"BOOL": True},
                                               "reason": {"S": "initial state: off until verified"}})
        if not KEYFILE.exists():
            KEYFILE.write_text(secrets.token_urlsafe(24), encoding="utf-8")
        h = hashlib.sha256(KEYFILE.read_text(encoding="utf-8").strip().encode()).hexdigest()
        db.put_item(TableName=TABLE, Item={"pk": {"S": f"key#{h}"}, "name": {"S": "demo"}, "daily_limit": {"N": "20"},
                                           "enabled": {"BOOL": True}})
        print("initialised (kill switch ON; demo key written to", KEYFILE.name + ")")
    if a.kill:
        db.put_item(TableName=TABLE, Item={"pk": {"S": "config#killswitch"}, "enabled": {"BOOL": a.kill == "on"},
                                           "reason": {"S": "set by seed_state.py"}})
        print("kill switch:", a.kill.upper())
        if not a.no_status:
            write_status(session, a.kill == "off", "live" if a.kill == "off" else "paused")
    if a.status:
        it = db.get_item(TableName=TABLE, Key={"pk": {"S": "config#killswitch"}}, ConsistentRead=True).get("Item", {})
        on = it.get("enabled", {}).get("BOOL", True)
        write_status(session, not on, "paused" if on else "live")
    if a.set:
        upd = dict(kv.split("=", 1) for kv in a.set)
        assert set(upd) <= set(LIMITS), f"unknown keys: {set(upd) - set(LIMITS)}"
        db.update_item(TableName=TABLE, Key={"pk": {"S": "config#global"}},
                       UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in upd),
                       ExpressionAttributeNames={f"#{k}": k for k in upd},
                       ExpressionAttributeValues={f":{k}": {"N": str(int(v))} for k, v in upd.items()})
        print("updated:", upd)
    if a.show or not (a.init or a.kill or a.set or a.status):
        for pk in ("config#global", "config#killswitch"):
            it = db.get_item(TableName=TABLE, Key={"pk": {"S": pk}}, ConsistentRead=True).get("Item", {})
            print(pk, {k: list(v.values())[0] for k, v in it.items() if k != "pk"})


if __name__ == "__main__":
    main()
