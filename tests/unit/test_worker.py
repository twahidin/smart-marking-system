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


# --- v2 dispatch: submissions whose assignment has a mark scheme / rubric ------------------------

class FakePipelineV2:
    def __init__(self, escalations):
        self.escalations = escalations
        self.calls = []

    def run(self, images, template, submission_id=None):
        self.calls.append((images, template, submission_id))
        from sms.pipeline.marking_pipeline_v2 import MarkingResultV2
        from sms.schemas.extraction import ExtractedScript
        from sms.schemas.marking_v2 import MarkedScriptV2
        return MarkingResultV2(run_id="r2", extracted=ExtractedScript(questions=[]),
                               final=MarkedScriptV2(kind="mark_scheme"), escalations=self.escalations)


def _keep_pages(store):
    """Turn the global delete-after-marking default off, so a `done` script keeps its pages."""
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0, delete_pages_after_marking=False))


def _template(db, kind="mark_scheme", subject="math"):
    return db.insert("INSERT INTO assignment_templates (title, subject, context, rubric_json, scheme_kind, questions_json, scheme_json) "
                     "VALUES ('T', :subj, 'ECF applies', '{\"criterion_defs\": []}', :k, :q, :s) RETURNING id",
                     {"subj": subject, "k": kind, "q": json.dumps([{"q_id": "1a", "text": "Solve", "max_marks": 2}]),
                      "s": json.dumps([{"q_id": "1a", "answer": "x=3", "marks": [{"label": "B2", "marks": 2}], "notes": ""}])})


def test_run_mark_job_uses_v2_pipeline_for_mark_scheme_assignment(env):
    db, store, storage, sid = env
    _keep_pages(store)  # the script is marked twice below
    tid = _template(db, "mark_scheme", subject="science")
    db.execute("UPDATE submissions SET assignment_id = ? WHERE id = ?", (tid, sid))
    fp = FakePipelineV2(escalations={})
    seen = {}

    def factory(**kw):
        seen.update(kw)
        return fp

    run_mark_job(db, storage, store, sid, pipeline_factory=factory)
    # the assignment's subject drives the v2 path (the submission row says 'math')
    assert seen["kind"] == "mark_scheme" and seen["subject"] == "science" and seen["db"] is db
    images, template, sub_id = fp.calls[0]
    assert images == [b"\xff\xd8\xffjpegbytes"] and sub_id == sid
    assert template["scheme_kind"] == "mark_scheme" and template["subject"] == "science" and template["context"] == "ECF applies"
    assert template["questions"][0]["q_id"] == "1a" and template["scheme"][0]["marks"][0]["label"] == "B2"
    row = db.query("SELECT status, run_id FROM submissions WHERE id = ?", (sid,))[0]
    assert row["status"] == "done" and row["run_id"] == "r2"
    # escalations (a dict for v2) put the script in the queue
    db.execute("UPDATE submissions SET status = 'uploaded'")
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipelineV2({"1a": "not in scheme"}))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "needs_you"


def test_run_mark_job_keeps_v1_for_criteria_or_no_assignment(env):
    db, store, storage, sid = env
    _keep_pages(store)  # the script is marked twice below
    tid = _template(db, "criteria")
    db.execute("UPDATE submissions SET assignment_id = ? WHERE id = ?", (tid, sid))
    seen = []

    def factory(**kw):
        seen.append(kw)
        return FakePipeline([])

    run_mark_job(db, storage, store, sid, pipeline_factory=factory)
    assert "kind" not in seen[0]
    assert db.query("SELECT status, marks_version FROM submissions WHERE id = ?", (sid,))[0] == {"status": "done", "marks_version": 1}
    # a dangling assignment_id (template deleted) also falls back to v1
    db.execute("UPDATE submissions SET assignment_id = 999999, status = 'uploaded' WHERE id = ?", (sid,))
    run_mark_job(db, storage, store, sid, pipeline_factory=factory)
    assert "kind" not in seen[1] and len(seen) == 2


def test_default_pipeline_factory_builds_v2_agents(env, monkeypatch):
    db, store, storage, sid = env
    from sms.worker import mark_job
    from sms.pipeline.marking_pipeline_v2 import MarkingPipelineV2
    from sms.providers.ratelimit import RateLimitedAgent
    pipeline = mark_job._default_pipeline_factory(db=db, settings=store.load(), subject="math", kind="rubric")
    assert isinstance(pipeline, MarkingPipelineV2) and pipeline.kind == "rubric"
    assert all(isinstance(a, RateLimitedAgent) for a in (pipeline.extractor, pipeline.marker, pipeline.reviewer, pipeline.feedback))
    from sms.pipeline.marking_pipeline import MarkingPipeline
    assert isinstance(mark_job._default_pipeline_factory(db=db, settings=store.load(), subject="math"), MarkingPipeline)


# --- deleting student pages once a script is done -------------------------------------------------

def _page_state(db, storage, sid):
    rows = db.query("SELECT deleted_at, storage_path FROM pages WHERE submission_id = ?", (sid,))
    return [(r["deleted_at"] is not None, storage.abs(r["storage_path"]).exists()) for r in rows]


def test_run_mark_job_deletes_pages_on_done_but_not_needs_you(env):
    db, store, storage, sid = env
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline(["q2"]))
    assert _page_state(db, storage, sid) == [(False, True)]
    db.execute("UPDATE submissions SET status = 'uploaded'")
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "done"
    assert _page_state(db, storage, sid) == [(True, False)]


def test_run_mark_job_respects_the_delete_flag(env):
    db, store, storage, sid = env
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=0, delete_pages_after_marking=False))
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "done"
    assert _page_state(db, storage, sid) == [(False, True)]
    # the assignment's own setting wins over the global default
    tid = _template(db, "mark_scheme")
    db.execute("UPDATE assignment_templates SET delete_pages_after_marking = 1 WHERE id = ?", (tid,))
    db.execute("UPDATE submissions SET assignment_id = ?, status = 'uploaded' WHERE id = ?", (tid, sid))
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipelineV2({}))
    assert _page_state(db, storage, sid) == [(True, False)]


def test_run_mark_job_done_survives_a_deletion_failure(env, monkeypatch):
    """Marking is finished: a deletion error must not fail (and re-run) the job — the sweep retries it."""
    db, store, storage, sid = env
    from sms.worker import mark_job

    def boom(*a, **k):
        raise RuntimeError("volume unavailable")

    monkeypatch.setattr(mark_job, "delete_submission_pages", boom)
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "done"
    assert _page_state(db, storage, sid) == [(False, True)]


def test_worker_sweeps_pages_at_most_once_per_hour(env, monkeypatch):
    db, store, storage, sid = env
    from sms.worker import worker as worker_mod
    calls = []
    monkeypatch.setattr(worker_mod, "sweep_done_submissions", lambda db_, storage_, older_than_hours=24: calls.append(older_than_hours) or 0)
    w = Worker(db, storage, store)
    w._maybe_sweep_pages()
    w._maybe_sweep_pages()
    assert calls == [24]
    w._last_page_sweep = None
    w._maybe_sweep_pages()
    assert calls == [24, 24]


def test_worker_sweep_really_deletes_old_done_pages(env):
    db, store, storage, sid = env
    db.execute("UPDATE submissions SET status = 'done', updated_at = ? WHERE id = ?",
               ((datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S"), sid))
    Worker(db, storage, store)._maybe_sweep_pages()
    assert _page_state(db, storage, sid) == [(True, False)]


def test_run_forever_runs_the_page_sweep(env):
    db, store, storage, sid = env
    w = Worker(db, storage, store, poll_s=0.01)
    stop = threading.Event()
    t = w.start_thread(stop)
    import time
    for _ in range(300):
        if w._last_page_sweep is not None:
            break
        time.sleep(0.01)
    stop.set(); t.join(timeout=2)
    assert w._last_page_sweep is not None


def test_run_mark_job_refuses_a_script_whose_pages_were_deleted(env):
    """Once the pages are gone there is nothing to mark: a clear, non-retryable error rather than a
    missing-file traceback."""
    db, store, storage, sid = env
    run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))
    assert _page_state(db, storage, sid) == [(True, False)]
    db.execute("UPDATE submissions SET status = 'uploaded'")
    with pytest.raises(RuntimeError, match="deleted after marking"):
        run_mark_job(db, storage, store, sid, pipeline_factory=lambda **kw: FakePipeline([]))
    assert db.query("SELECT status FROM submissions WHERE id = ?", (sid,))[0]["status"] == "uploaded"
