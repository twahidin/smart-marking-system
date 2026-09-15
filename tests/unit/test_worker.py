import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import Settings, SettingsStore
from sms.storage import PageStorage
from sms.worker.jobs import JobStore
from sms.worker.mark_job import run_mark_job
from sms.worker.worker import Worker


@pytest.fixture
def env(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0))
    storage = PageStorage(tmp_path / "data")
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) VALUES "
                    "('s', 'math', 'ctx', '{\"criterion_defs\": [{\"id\": \"c1\", \"description\": \"d\", \"max_score\": 2}]}', 'uploaded') RETURNING id")
    digest, rel = storage.put_jpeg(b"\xff\xd8\xffjpegbytes")
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) VALUES (?, 0, ?, ?, 10, 10)",
               (sid, digest, rel))
    return db, store, storage, sid


class FakePipeline:
    def __init__(self, escalations):
        self.escalations = escalations
        self.calls = []

    def run(self, images, assignment_context, rubric, submission_id=None):
        self.calls.append((images, assignment_context, rubric, submission_id))
        from sms.pipeline.marking_pipeline import MarkingResult
        from sms.schemas.extraction import ExtractedScript
        from sms.schemas.marking import MarkedScript
        return MarkingResult(run_id="r1", extracted=ExtractedScript(questions=[]),
                             final_marks=MarkedScript(marks=[]), escalations=self.escalations)


def test_run_mark_job_done(env):
    db, store, storage, sid = env
    fp = FakePipeline(escalations=[])
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: fp)
    assert fp.calls[0][0] == [b"\xff\xd8\xffjpegbytes"] and fp.calls[0][3] == sid
    row = db.query("SELECT status, run_id FROM submissions WHERE id = ?", (sid,))[0]
    assert row["status"] == "done" and row["run_id"] == "r1"


def test_run_mark_job_needs_you(env):
    db, store, storage, sid = env
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline(["q2"]))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "needs_you"


def test_run_mark_job_without_key_raises_non_retryable(env):
    db, store, storage, sid = env
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=0))
    db.execute("UPDATE settings SET api_key_enc = NULL")
    with pytest.raises(RuntimeError, match="API key"):
        run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))


def test_worker_success_path(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)
    w = Worker(db, storage, store, runner=lambda *a, **k: None)
    assert w.run_once() is True
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert w.run_once() is False


def test_worker_retryable_error_requeues_with_backoff(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)
    import httpx, openai
    err = openai.APIStatusError("rl", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None)

    def runner(*a, **k):
        raise err

    w = Worker(db, storage, store, runner=runner)
    w.run_once()
    row = db.query("SELECT status, attempts, not_before, error FROM jobs")[0]
    assert row["status"] == "queued" and row["attempts"] == 1 and row["not_before"] and "429" in row["error"]


def test_worker_non_retryable_fails(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("mark", sid)

    def runner(*a, **k):
        raise ValueError("bad rubric")

    Worker(db, storage, store, runner=runner).run_once()
    assert db.query("SELECT status FROM jobs")[0]["status"] == "failed"
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "failed"


def test_worker_gives_up_after_max_attempts(env):
    db, store, storage, sid = env
    js = JobStore(db)
    jid = js.enqueue("mark", sid)
    db.execute("UPDATE jobs SET attempts = 4 WHERE id = ?", (jid,))

    def runner(*a, **k):
        raise TimeoutError()

    Worker(db, storage, store, runner=runner).run_once()
    assert db.query("SELECT status FROM jobs")[0]["status"] == "failed"


def test_worker_resets_running_on_start_and_heartbeats(env):
    db, store, storage, sid = env
    js = JobStore(db)
    js.enqueue("mark", sid)
    js.claim()
    stop = threading.Event()
    w = Worker(db, storage, store, runner=lambda *a, **k: None, poll_s=0.01)
    t = w.start_thread(stop)
    import time
    for _ in range(200):
        if db.query("SELECT status FROM jobs")[0]["status"] == "done":
            break
        time.sleep(0.01)
    stop.set(); t.join(timeout=2)
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert js.last_heartbeat()


def test_worker_retries_reset_running_on_db_outage_then_recovers(env):
    """reset_running() failing on the first attempt (e.g. a brief DB outage at startup)
    must not kill the worker thread — it should keep retrying the reset each iteration
    (inside the same try/except that logs 'worker loop error') and only claim jobs once
    the reset finally succeeds."""
    db, store, storage, sid = env
    js = JobStore(db)
    js.enqueue("mark", sid)
    js.claim()  # simulate a job left "running" by a crashed previous worker

    orig_reset_running = js.reset_running
    calls = {"n": 0}

    def flaky_reset_running():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db unreachable")
        return orig_reset_running()

    js.reset_running = flaky_reset_running

    stop = threading.Event()
    w = Worker(db, storage, store, runner=lambda *a, **k: None, poll_s=0.01)
    w.jobs = js
    t = w.start_thread(stop)
    import time
    for _ in range(300):
        if db.query("SELECT status FROM jobs")[0]["status"] == "done":
            break
        time.sleep(0.01)
    stop.set(); t.join(timeout=2)
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"
    assert calls["n"] >= 2
    assert js.last_heartbeat()


def test_worker_reuses_rate_limit_bucket_across_jobs_until_rpm_changes(env):
    db, store, storage, sid = env
    js = JobStore(db)
    js.enqueue("mark", sid)
    js.enqueue("mark", sid)

    seen_buckets = []

    def runner(*a, **k):
        seen_buckets.append(k["bucket"])

    w = Worker(db, storage, store, runner=runner)
    w.run_once()
    w.run_once()
    assert seen_buckets[0] is seen_buckets[1]
    assert seen_buckets[0].rpm == 0

    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=5))
    js.enqueue("mark", sid)
    w.run_once()
    assert seen_buckets[2] is not seen_buckets[0]
    assert seen_buckets[2].rpm == 5


# --- reflect jobs and the nightly scheduler ------------------------------------------------------

def _corrections(db, subject="math", run_id="r1", age_hours=0):
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, final_status) VALUES (?, 'complete', ?, '{}', 'complete')",
               (run_id, subject))
    db.execute("INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason, created_at) "
               "VALUES (?, 'q1', 1, 2, 'x', ?)",
               (run_id, (datetime.now(timezone.utc) - timedelta(hours=age_hours)).strftime("%Y-%m-%d %H:%M:%S")))


def test_worker_dispatches_reflect_job_with_payload(env):
    db, store, storage, sid = env
    js = JobStore(db)
    jid = js.enqueue("reflect", payload={"subject": "science", "lookback_days": 3})
    assert db.query("SELECT submission_id, payload_json FROM jobs WHERE id = ?", (jid,))[0]["submission_id"] is None
    seen = []

    def reflect_runner(db_, store_, subject, lookback_days, bucket=None, run_id=None):
        seen.append((subject, lookback_days, bucket, run_id))
        return 0

    w = Worker(db, storage, store, runner=lambda *a, **k: pytest.fail("mark runner must not run"), reflect_runner=reflect_runner)
    assert w.run_once() is True
    # the worker opens the reflection_runs row up front and hands its id to the runner
    run = db.query("SELECT id, subject, lookback_days FROM reflection_runs")[0]
    assert run["subject"] == "science" and run["lookback_days"] == 3
    assert seen == [("science", 3, w._bucket, run["id"])]
    assert db.query("SELECT status FROM jobs WHERE id = ?", (jid,))[0]["status"] == "done"
    # the submission row is untouched by a job without a submission_id
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "uploaded"


def test_worker_reflect_failure_is_recorded_without_touching_submissions(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("reflect", payload={"subject": "math", "lookback_days": 7})

    def reflect_runner(*a, **k):
        raise ValueError("boom")

    Worker(db, storage, store, reflect_runner=reflect_runner).run_once()
    assert db.query("SELECT status, error FROM jobs")[0] == {"status": "failed", "error": "boom"}
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "uploaded"


def test_worker_reflect_retry_reuses_the_same_run_row(env):
    db, store, storage, sid = env
    JobStore(db).enqueue("reflect", payload={"subject": "math", "lookback_days": 7})
    import httpx, openai
    err = openai.APIStatusError("rl", response=httpx.Response(429, request=httpx.Request("POST", "https://x")), body=None)
    seen_run_ids = []

    def reflect_runner(db_, store_, subject, lookback_days, bucket=None, run_id=None):
        seen_run_ids.append(run_id)
        if len(seen_run_ids) == 1:
            raise err
        return 0

    w = Worker(db, storage, store, reflect_runner=reflect_runner)
    w.run_once()
    job = db.query("SELECT status, payload_json FROM jobs")[0]
    assert job["status"] == "queued" and json.loads(job["payload_json"])["run_id"] == seen_run_ids[0]
    db.execute("UPDATE jobs SET not_before = NULL")
    w.run_once()
    assert seen_run_ids[0] == seen_run_ids[1]
    assert db.query("SELECT COUNT(*) AS c FROM reflection_runs")[0]["c"] == 1
    assert db.query("SELECT status FROM jobs")[0]["status"] == "done"


def test_scheduler_enqueues_once_per_subject_with_recent_corrections(env):
    db, store, storage, sid = env
    _corrections(db, "math", "r1")
    _corrections(db, "science", "r2", age_hours=30)  # too old
    w = Worker(db, storage, store)
    w._maybe_schedule_reflection()
    jobs = db.query("SELECT kind, status, payload_json FROM jobs")
    assert len(jobs) == 1 and jobs[0]["kind"] == "reflect"
    assert json.loads(jobs[0]["payload_json"]) == {"subject": "math", "lookback_days": 7}
    # a second check (throttle bypassed) does not duplicate the queued job
    w._last_reflect_check = None
    w._maybe_schedule_reflection()
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 1
    # once the job has run and a reflection_runs row exists, nothing new is scheduled for 24 h
    w.reflect_runner = lambda *a, **k: db.execute("INSERT INTO reflection_runs (subject, lookback_days, proposed_notes, finished_at) "
                                                  "VALUES ('math', 7, 0, CURRENT_TIMESTAMP)")
    w.run_once()
    w._last_reflect_check = None
    w._maybe_schedule_reflection()
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 1
    # a new correction after a stale (>24 h) run schedules again
    db.execute("UPDATE reflection_runs SET started_at = ?",
               ((datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S"),))
    w._last_reflect_check = None
    w._maybe_schedule_reflection()
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 2
    # a failed run in the last 24 h does not count as "ran": it is retried on the next pass
    db.execute("UPDATE jobs SET status = 'done'")
    db.execute("INSERT INTO reflection_runs (subject, lookback_days, finished_at, error) VALUES ('math', 7, CURRENT_TIMESTAMP, 'boom')")
    w._last_reflect_check = None
    w._maybe_schedule_reflection()
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 3


def test_scheduler_is_throttled_and_respects_auto_reflect(env):
    db, store, storage, sid = env
    _corrections(db, "math", "r1")
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0, auto_reflect=False))
    w = Worker(db, storage, store)
    w._maybe_schedule_reflection()
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 0
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0, auto_reflect=True))
    w._maybe_schedule_reflection()  # within the 10-minute throttle window: no check
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 0
    w._last_reflect_check = None
    w._maybe_schedule_reflection()
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 1


def test_scheduler_skips_without_api_key(env):
    db, store, storage, sid = env
    _corrections(db, "math", "r1")
    db.execute("UPDATE settings SET api_key_enc = NULL")
    Worker(db, storage, store)._maybe_schedule_reflection()
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == 0


def test_run_forever_calls_scheduler(env):
    db, store, storage, sid = env
    _corrections(db, "math", "r1")
    w = Worker(db, storage, store, reflect_runner=lambda *a, **k: 0, poll_s=0.01)
    stop = threading.Event()
    t = w.start_thread(stop)
    import time
    for _ in range(300):
        rows = db.query("SELECT status FROM jobs WHERE kind = 'reflect'")
        if rows and rows[0]["status"] == "done":
            break
        time.sleep(0.01)
    stop.set(); t.join(timeout=2)
    assert db.query("SELECT status FROM jobs WHERE kind = 'reflect'")[0]["status"] == "done"
