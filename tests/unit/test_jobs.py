import pytest

from sms.memory.db import Database
from sms.worker.jobs import JobStore


@pytest.fixture
def db(tmp_path):
    return Database(path=str(tmp_path / "s.db"))


def _submission(db):
    return db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                     "VALUES ('s', 'math', '', '{}', 'uploaded') RETURNING id")


def test_enqueue_claim_finish(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    job = js.claim()
    assert job["id"] == jid and job["status"] == "running" and job["attempts"] == 1
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "marking"
    assert js.claim() is None
    js.finish(jid)
    assert db.query("SELECT status, finished_at FROM jobs WHERE id = ?", (jid,))[0]["status"] == "done"


def test_retry_later_respects_not_before(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    js.claim()
    js.retry_later(jid, delay_s=3600, error="HTTP 429")
    row = db.query("SELECT status, error, not_before FROM jobs WHERE id = ?", (jid,))[0]
    assert row["status"] == "queued" and row["error"] == "HTTP 429" and row["not_before"]
    assert js.claim() is None
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "queued"
    js.retry_later(jid, delay_s=0, error="x")
    assert js.claim()["id"] == jid


def test_fail_marks_submission_failed(db):
    js = JobStore(db)
    sid = _submission(db)
    jid = js.enqueue("mark", sid)
    js.claim()
    js.fail(jid, "boom")
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "failed"
    assert js.job_for_submission(sid)["error"] == "boom"


def test_reset_running(db):
    js = JobStore(db)
    sid = _submission(db)
    js.enqueue("mark", sid)
    js.claim()
    assert js.reset_running() == 1
    assert js.claim() is not None


def test_heartbeat(db):
    js = JobStore(db)
    assert js.last_heartbeat() is None
    js.heartbeat()
    assert js.last_heartbeat()
    js.heartbeat()
    assert db.query("SELECT COUNT(*) AS c FROM worker_heartbeat")[0]["c"] == 1


def test_last_heartbeat_is_iso_utc(db):
    js = JobStore(db)
    js.heartbeat()
    seen = js.last_heartbeat()
    assert len(seen) == 20 and seen[10] == "T" and seen.endswith("Z")


def test_claim_orders_by_created(db):
    js = JobStore(db)
    a = js.enqueue("mark", _submission(db))
    b = js.enqueue("mark", _submission(db))
    assert js.claim()["id"] == a and js.claim()["id"] == b


def test_enqueue_unique_blocks_same_key_while_active_then_allows_after_finish(db):
    js = JobStore(db)
    a = js.enqueue_unique("reflect", {"subject": "math", "lookback_days": 7}, dedupe_key="reflect:math")
    assert isinstance(a, int)
    # same key, different payload (e.g. a retry that gained run_id): still a duplicate while queued
    assert js.enqueue_unique("reflect", {"subject": "math", "lookback_days": 14, "run_id": 3}, dedupe_key="reflect:math") is None
    assert js.enqueue_unique("reflect", {"subject": "science", "lookback_days": 7}, dedupe_key="reflect:science") is not None
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 2
    # ...and while running
    js.claim()
    assert js.enqueue_unique("reflect", {"subject": "math", "lookback_days": 7}, dedupe_key="reflect:math") is None
    # the index only covers queued/running: a finished job no longer blocks a new one
    js.finish(a)
    b = js.enqueue_unique("reflect", {"subject": "math", "lookback_days": 7}, dedupe_key="reflect:math")
    assert isinstance(b, int) and b != a
    assert db.query("SELECT dedupe_key FROM jobs WHERE id = ?", (b,))[0]["dedupe_key"] == "reflect:math"


def test_enqueue_unique_failed_job_does_not_block(db):
    js = JobStore(db)
    a = js.enqueue_unique("reflect", {"subject": "math"}, dedupe_key="reflect:math")
    js.claim()
    js.fail(a, "boom")
    assert js.enqueue_unique("reflect", {"subject": "math"}, dedupe_key="reflect:math") is not None


def test_enqueue_unique_under_concurrency_creates_one_job(db):
    import threading
    js = JobStore(db)
    results = []
    start = threading.Barrier(8)

    def go():
        start.wait()
        results.append(js.enqueue_unique("reflect", {"subject": "math", "lookback_days": 7}, dedupe_key="reflect:math"))

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len([r for r in results if r is not None]) == 1
    assert db.query("SELECT COUNT(*) AS c FROM jobs WHERE kind = 'reflect'")[0]["c"] == 1


def test_set_payload_rewrites_payload_json(db):
    js = JobStore(db)
    jid = js.enqueue("reflect", payload={"subject": "math"})
    js.set_payload(jid, {"subject": "math", "run_id": 4})
    assert db.query("SELECT payload_json FROM jobs WHERE id = ?", (jid,))[0]["payload_json"] == '{"run_id": 4, "subject": "math"}'
