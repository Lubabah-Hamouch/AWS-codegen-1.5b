"""Request guardrails, enforced before any generation work starts. All state lives in one DynamoDB table.

    adm = admit(api_key, client_ip)
    if not adm.ok: respond(adm.status, {"error": adm.message, "code": adm.code})
    try: ...stream...
    finally: release(adm)

Checks, in order (each failure is a hard stop, and every unexpected error fails closed):
  1. kill switch      config#killswitch {enabled: true}
  2. identity         api key -> key#<sha256> {name, daily_limit, enabled}; no key -> anonymous tier, limited per IP
  3. concurrency slot slot#0..N-1, claimed with a conditional put; a slot expires on its own, so a crashed
                      invocation cannot leak capacity. N = config#global.max_concurrency
  4. daily counters   one transaction over (global, subject[, anon total]); any counter at its limit cancels it

Denial codes (stable, for clients): disabled 503, invalid_key 401, busy 429, daily_capacity 429, daily_limit 429,
unavailable 503 (failed closed).

This replaces Lambda reserved concurrency, which this account cannot use yet (quota of 10, AWS needs 100 unreserved).
"""

import hashlib
import os
import random
import time
import uuid
from dataclasses import dataclass, field

import boto3
from botocore.exceptions import ClientError

TABLE = os.environ.get("TABLE_NAME", "codegen-state")
DEFAULTS = {"global_daily": 200, "max_concurrency": 2, "slot_seconds": 60, "max_tokens": 512,
            "anon_total_daily": 100, "anon_ip_daily": 5}
COUNTER_TTL_S = 3 * 86400

_client = None


def ddb():
    global _client
    if _client is None:
        _client = boto3.client("dynamodb", endpoint_url=os.environ.get("DDB_ENDPOINT") or None,
                               region_name=os.environ.get("AWS_REGION") or "eu-north-1")
    return _client


@dataclass
class Admission:
    ok: bool
    status: int = 200
    message: str = ""
    code: str = ""
    subject: str = ""
    max_tokens: int = DEFAULTS["max_tokens"]
    slot: str = ""
    token: str = ""
    counters: list = field(default_factory=list)
    remaining: int | None = None  # the subject's runs left today, best effort


def _deny(status: int, code: str, message: str, **kw) -> Admission:
    return Admission(False, status, message, code, **kw)


def _n(item: dict, key: str, default):
    return int(item[key]["N"]) if key in item else default


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _load(keys: list) -> dict:
    resp = ddb().batch_get_item(RequestItems={TABLE: {"Keys": [{"pk": {"S": k}} for k in keys], "ConsistentRead": True}})
    if resp.get("UnprocessedKeys"):
        raise RuntimeError("unprocessed keys")  # fail closed
    return {i["pk"]["S"]: i for i in resp["Responses"][TABLE]}


def _acquire_slot(n: int, token: str, now: int, lease_s: int) -> str:
    order = list(range(n))
    random.shuffle(order)
    for i in order:
        try:
            ddb().put_item(
                TableName=TABLE,
                Item={"pk": {"S": f"slot#{i}"}, "owner": {"S": token}, "expires": {"N": str(now + lease_s)},
                      "ttl": {"N": str(now + lease_s + 3600)}},
                ConditionExpression="attribute_not_exists(pk) OR expires < :now",
                ExpressionAttributeValues={":now": {"N": str(now)}})
            return f"slot#{i}"
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
    return ""


def _release_slot(slot: str, token: str) -> None:
    try:
        ddb().delete_item(TableName=TABLE, Key={"pk": {"S": slot}}, ConditionExpression="#o = :t",
                          ExpressionAttributeNames={"#o": "owner"}, ExpressionAttributeValues={":t": {"S": token}})
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def admit(api_key: str | None, client_ip: str, now: int | None = None) -> Admission:
    try:
        return _admit(api_key, client_ip, int(now if now is not None else time.time()))
    except Exception as e:  # unreachable table, throttling, bad data: refuse rather than run unguarded
        print(f"[guard] fail closed: {type(e).__name__}: {e}", flush=True)
        return _deny(503, "unavailable", "service unavailable")


def _admit(api_key, client_ip, now) -> Admission:
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    key_pk = f"key#{_hash(api_key)}" if api_key else None
    items = _load(["config#killswitch", "config#global"] + ([key_pk] if key_pk else []))

    kill = items.get("config#killswitch")
    if kill and kill.get("enabled", {}).get("BOOL"):
        return _deny(503, "disabled", "service disabled")
    cfg = {k: _n(items.get("config#global", {}), k, v) for k, v in DEFAULTS.items()}

    if key_pk:
        key = items.get(key_pk)
        if not key or key.get("enabled", {}).get("BOOL") is False:
            return _deny(401, "invalid_key", "invalid api key")
        subject, subject_limit, tier_total = f"key#{key['name']['S']}", _n(key, "daily_limit", 20), None
    else:
        subject, subject_limit, tier_total = f"ip#{_hash(client_ip)[:16]}", cfg["anon_ip_daily"], cfg["anon_total_daily"]

    token = uuid.uuid4().hex
    slot = _acquire_slot(cfg["max_concurrency"], token, now, cfg["slot_seconds"])
    if not slot:
        return _deny(429, "busy", "busy, retry shortly")

    ttl = str(now + COUNTER_TTL_S)
    counters = [("global", f"day#{day}#global", cfg["global_daily"]), ("subject", f"day#{day}#{subject}", subject_limit)]
    if tier_total is not None:
        counters.append(("anonymous total", f"day#{day}#anon-total", tier_total))
    try:
        ddb().transact_write_items(TransactItems=[
            {"Update": {"TableName": TABLE, "Key": {"pk": {"S": pk}},
                        "UpdateExpression": "ADD n :one SET #t = :ttl",
                        "ConditionExpression": "attribute_not_exists(n) OR n < :lim",
                        "ExpressionAttributeNames": {"#t": "ttl"},
                        "ExpressionAttributeValues": {":one": {"N": "1"}, ":ttl": {"N": ttl}, ":lim": {"N": str(lim)}}}}
            for _, pk, lim in counters])
    except ClientError as e:
        _release_slot(slot, token)
        if e.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        reasons = e.response.get("CancellationReasons", [])
        failed = [counters[i][0] for i, r in enumerate(reasons) if r.get("Code") == "ConditionalCheckFailed"]
        if not failed:
            raise
        if "global" in failed or "anonymous total" in failed:
            return _deny(429, "daily_capacity", "daily capacity reached")
        return _deny(429, "daily_limit", "daily limit reached", remaining=0)
    return Admission(True, 200, "ok", "", subject, cfg["max_tokens"], slot, token, [pk for _, pk, _ in counters],
                     _remaining(counters[1][1], subject_limit))


def _remaining(pk: str, limit: int) -> int | None:
    # The transaction cannot return the new count; one consistent read can. Purely informational, so never fatal.
    try:
        item = ddb().get_item(TableName=TABLE, Key={"pk": {"S": pk}}, ConsistentRead=True).get("Item", {})
        return max(limit - _n(item, "n", 0), 0)
    except Exception as e:
        print(f"[guard] remaining unknown: {e}", flush=True)
        return None


def release(adm: Admission) -> None:
    if adm.ok and adm.slot:
        try:
            _release_slot(adm.slot, adm.token)
        except Exception as e:  # the slot lease expires on its own
            print(f"[guard] release failed (lease will expire): {e}", flush=True)
