"""Guardrail tests against DynamoDB Local.

    docker run -d --name ddb-local -p 8000:8000 amazon/dynamodb-local
    DDB_ENDPOINT=http://localhost:8000 python -m pytest backend/tests -q

Skipped when DynamoDB Local is not reachable, unless REQUIRE_DDB is set (CI), which makes that a failure.
"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("DDB_ENDPOINT", "http://localhost:8000")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "x")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "x")
os.environ.setdefault("AWS_REGION", "eu-north-1")
os.environ["TABLE_NAME"] = "guard-test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import guard  # noqa: E402

NOW = 1_800_000_000


def put(pk, **attrs):
    item = {"pk": {"S": pk}}
    for k, v in attrs.items():
        item[k] = {"BOOL": v} if isinstance(v, bool) else {"N": str(v)} if isinstance(v, int) else {"S": v}
    guard.ddb().put_item(TableName=guard.TABLE, Item=item)


@pytest.fixture(autouse=True)
def table():
    c = guard.ddb()
    try:
        c.delete_table(TableName=guard.TABLE)
    except Exception:
        pass
    try:
        c.create_table(TableName=guard.TABLE, KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                       AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
    except Exception as e:
        if os.environ.get("REQUIRE_DDB"):  # CI: a skip would read as a pass
            pytest.fail(f"DynamoDB Local not reachable: {e}")
        pytest.skip(f"DynamoDB Local not reachable: {e}")
    yield


def test_anonymous_allowed_then_per_ip_limit():
    put("config#global", anon_ip_daily=3, max_concurrency=5)
    for left in (2, 1, 0):
        a = guard.admit(None, "1.2.3.4", NOW)
        assert a.ok and a.remaining == left
        guard.release(a)
    a = guard.admit(None, "1.2.3.4", NOW)
    assert (a.ok, a.status, a.code, a.message, a.remaining) == (False, 429, "daily_limit", "daily limit reached", 0)
    assert guard.admit(None, "5.6.7.8", NOW).ok  # other IPs unaffected


def test_global_daily_cap_blocks_everyone():
    put("config#global", global_daily=2, max_concurrency=5)
    for ip in ("a", "b"):
        guard.release(guard.admit(None, ip, NOW))
    a = guard.admit(None, "c", NOW)
    assert (a.ok, a.status, a.code, a.message) == (False, 429, "daily_capacity", "daily capacity reached")


def test_counters_reset_next_day():
    put("config#global", anon_ip_daily=1, max_concurrency=5)
    guard.release(guard.admit(None, "1.1.1.1", NOW))
    assert not guard.admit(None, "1.1.1.1", NOW).ok
    assert guard.admit(None, "1.1.1.1", NOW + 86400).ok


def test_denied_request_does_not_consume_quota():
    put("config#global", global_daily=10, anon_ip_daily=1, max_concurrency=5)
    guard.release(guard.admit(None, "9.9.9.9", NOW))
    for _ in range(3):
        assert not guard.admit(None, "9.9.9.9", NOW).ok
    day =time.strftime("%Y-%m-%d", time.gmtime(NOW))
    item = guard.ddb().get_item(TableName=guard.TABLE, Key={"pk": {"S": f"day#{day}#global"}}, ConsistentRead=True)
    assert item["Item"]["n"]["N"] == "1"  # the transaction is all-or-nothing


def test_concurrency_slots_and_release():
    put("config#global", max_concurrency=2)
    a, b = guard.admit(None, "a", NOW), guard.admit(None, "b", NOW)
    assert a.ok and b.ok and a.slot != b.slot
    c = guard.admit(None, "c", NOW)
    assert (c.ok, c.status, c.code) == (False, 429, "busy")
    guard.release(a)
    assert guard.admit(None, "c", NOW).ok


def test_slot_lease_expires_without_release():
    put("config#global", max_concurrency=1, slot_seconds=30)
    assert guard.admit(None, "a", NOW).ok  # never released: simulates a crashed invocation
    assert not guard.admit(None, "b", NOW + 10).ok
    assert guard.admit(None, "b", NOW + 31).ok


def test_release_only_by_owner():
    put("config#global", max_concurrency=1, slot_seconds=30)
    a = guard.admit(None, "a", NOW)
    stale = guard.Admission(True, slot=a.slot, token="someone-else")
    guard.release(stale)
    assert not guard.admit(None, "b", NOW).ok


def test_parallel_admissions_never_exceed_slots():
    put("config#global", max_concurrency=3, global_daily=1000, anon_ip_daily=1000, anon_total_daily=1000)
    results = []
    barrier = threading.Barrier(12)

    def go(i):
        barrier.wait()
        results.append(guard.admit(None, f"ip{i}", NOW))

    ts = [threading.Thread(target=go, args=(i,)) for i in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(r.ok for r in results) == 3


def test_kill_switch():
    put("config#global", max_concurrency=5)
    assert guard.admit(None, "a", NOW).ok
    put("config#killswitch", enabled=True)
    a = guard.admit(None, "a", NOW)
    assert (a.ok, a.status, a.code) == (False, 503, "disabled")
    put("config#killswitch", enabled=False)
    assert guard.admit(None, "a", NOW).ok


def test_api_key_valid_invalid_disabled_and_limit():
    put("config#global", max_concurrency=5)
    put(f"key#{guard._hash('secret-demo')}", name="demo", daily_limit=2, enabled=True)
    put(f"key#{guard._hash('revoked')}", name="old", daily_limit=9, enabled=False)
    assert (guard.admit("nope", "x", NOW).status, guard.admit("nope", "x", NOW).code) == (401, "invalid_key")
    assert guard.admit("revoked", "x", NOW).status == 401
    for _ in range(2):
        a = guard.admit("secret-demo", "x", NOW)
        assert a.ok and a.subject == "key#demo"
        guard.release(a)
    assert guard.admit("secret-demo", "x", NOW).code == "daily_limit"


def test_fails_closed_when_table_unreachable(monkeypatch):
    monkeypatch.setattr(guard, "TABLE", "table-that-does-not-exist")
    a = guard.admit(None, "a", NOW)
    assert (a.ok, a.status, a.code) == (False, 503, "unavailable")
