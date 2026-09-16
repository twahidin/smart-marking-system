"""Postgres smoke test — opt-in, runs only when SMS_TEST_DATABASE_URL points at a real Postgres.

    SMS_TEST_DATABASE_URL=postgresql://sms:sms@localhost:5432/sms_test uv run pytest tests/postgres -q

Exercises the code paths that differ between SQLite and Postgres: RETURNING, FOR UPDATE SKIP LOCKED,
ON CONFLICT against a partial unique index, aggregate types (Decimal/bigint), datetime columns, and the
partial unique index that keeps a student to one hand-in per class assignment.
"""
import os

import pytest
from sqlalchemy.exc import IntegrityError

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


def test_second_hand_in_for_the_same_student_and_assignment_raises_integrity_error(db):
    # hand_in relies on uq_submissions_student_assignment (partial, WHERE both columns are NOT NULL) to turn a
    # raced second tap into a 409; a plain SQLite run cannot prove the index exists on Postgres.
    class_id = db.insert("INSERT INTO classes (name, code) VALUES ('pg-smoke class', 'PGSM') RETURNING id")
    try:
        student_id = db.insert(
            "INSERT INTO students (class_id, reg_no, name) VALUES (:c, 1, 'pg-smoke student') RETURNING id",
            {"c": class_id},
        )
        ca_id = db.insert(
            "INSERT INTO class_assignments (class_id, template_id, title, status) "
            "VALUES (:c, 0, 'pg-smoke assignment', 'open') RETURNING id",
            {"c": class_id},
        )
        insert = (
            "INSERT INTO submissions (label, subject, context, rubric_json, status, class_assignment_id, student_id, "
            "source, handed_in_at) VALUES ('pg-smoke hand-in', 'math', '', '{}', 'uploaded', :ca, :st, 'student', "
            "CURRENT_TIMESTAMP) RETURNING id"
        )
        first = db.insert(insert, {"ca": ca_id, "st": student_id})
        assert isinstance(first, int)
        with pytest.raises(IntegrityError):
            db.insert(insert, {"ca": ca_id, "st": student_id})
        assert db.query(
            "SELECT COUNT(*) AS c FROM submissions WHERE class_assignment_id = :ca AND student_id = :st",
            {"ca": ca_id, "st": student_id},
        )[0]["c"] == 1
    finally:
        db.execute("DELETE FROM submissions WHERE class_assignment_id IN (SELECT id FROM class_assignments WHERE class_id = :c)",
                   {"c": class_id})
        # students and class_assignments cascade from the class
        db.execute("DELETE FROM classes WHERE id = :c", {"c": class_id})
