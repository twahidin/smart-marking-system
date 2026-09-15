"""Postgres smoke test — opt-in, runs only when SMS_TEST_DATABASE_URL points at a real Postgres.

    SMS_TEST_DATABASE_URL=postgresql://sms:sms@localhost:5432/sms_test uv run pytest tests/postgres -q

Exercises the code paths that differ between SQLite and Postgres: RETURNING, FOR UPDATE SKIP LOCKED,
ON CONFLICT against a partial unique index, aggregate types (Decimal/bigint), and datetime columns.
"""
import os

import pytest

from sms.memory.db import Database
from sms.memory.metrics import MetricsSummary, record_run_metric
from sms.timeutil import iso_utc
from sms.worker.jobs import JobStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("SMS_TEST_DATABASE_URL"),
    reason="set SMS_TEST_DATABASE_URL to a Postgres URL to run",
)


@pytest.fixture
def db():
    d = Database(url=os.environ["SMS_TEST_DATABASE_URL"])
    assert not d.is_sqlite
    yield d
    d.dispose()


@pytest.fixture
def submission_id(db):
    sid = db.insert(
        "INSERT INTO submissions (label, subject, context, rubric_json, status) "
        "VALUES ('pg-smoke', 'math', '', '{}', 'uploaded') RETURNING id"
    )
    yield sid
    db.execute("DELETE FROM jobs WHERE submission_id = :s", {"s": sid})
    db.execute("DELETE FROM submissions WHERE id = :s", {"s": sid})


def test_insert_returning_id_is_int(submission_id):
    assert isinstance(submission_id, int) and submission_id >= 1


def test_job_enqueue_claim_finish(db, submission_id):
    js = JobStore(db)
    jid = js.enqueue("mark", submission_id)
    job = js.claim()
    assert job is not None and job["id"] == jid and job["status"] == "running"
    assert db.query("SELECT status FROM submissions WHERE id = :s", {"s": submission_id})[0]["status"] == "marking"
    js.finish(jid)
    row = db.query("SELECT status, finished_at FROM jobs WHERE id = :j", {"j": jid})[0]
    assert row["status"] == "done" and row["finished_at"] is not None


def test_metrics_summary_returns_plain_numbers(db):
    run_id = "pg-smoke-run"
    try:
        record_run_metric(db, run_id, "mark", "pg_smoke_role", 120, 10, 5)
        record_run_metric(db, run_id, "mark", "pg_smoke_role", 80, 20, 15)
        s = MetricsSummary(db).summarize("pg_smoke_role")
        assert type(s["count"]) is int and s["count"] == 2
        assert type(s["mean_latency_ms"]) is float and s["mean_latency_ms"] == 100.0
        assert type(s["total_tokens_in"]) is int and s["total_tokens_in"] == 30
        assert type(s["total_tokens_out"]) is int and s["total_tokens_out"] == 20
    finally:
        db.execute("DELETE FROM agent_metrics WHERE run_id = :r", {"r": run_id})


def test_created_at_default_renders_as_utc_z(db, submission_id):
    row = db.query("SELECT created_at FROM submissions WHERE id = :s", {"s": submission_id})[0]
    rendered = iso_utc(row["created_at"])
    assert rendered is not None and rendered.endswith("Z") and rendered[10] == "T"
    # The engine pins the session timezone so now()-based defaults are UTC regardless of server config.
    assert db.query("SELECT current_setting('TimeZone') AS tz")[0]["tz"] == "UTC"


def test_enqueue_unique_is_backed_by_the_partial_unique_index(db):
    js = JobStore(db)
    key = "reflect:pg-smoke"
    db.execute("DELETE FROM jobs WHERE dedupe_key = :k", {"k": key})
    try:
        a = js.enqueue_unique("reflect", {"subject": "pg-smoke", "lookback_days": 7}, dedupe_key=key)
        assert isinstance(a, int)
        assert js.enqueue_unique("reflect", {"subject": "pg-smoke", "lookback_days": 7, "run_id": 1}, dedupe_key=key) is None
        js.finish(a)
        b = js.enqueue_unique("reflect", {"subject": "pg-smoke", "lookback_days": 7}, dedupe_key=key)
        assert isinstance(b, int) and b != a
        assert db.query("SELECT COUNT(*) AS c FROM jobs WHERE dedupe_key = :k", {"k": key})[0]["c"] == 2
    finally:
        db.execute("DELETE FROM jobs WHERE dedupe_key = :k", {"k": key})
