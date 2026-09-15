import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.providers.errors import error_message, is_retryable
from sms.providers.ratelimit import TokenBucket
from sms.providers.settings import SettingsStore
from sms.storage import PageStorage
from sms.worker.jobs import MAX_ATTEMPTS, JobStore
from sms.worker.mark_job import run_mark_job
from sms.worker.reflect_job import open_reflection_run, run_reflect_job

log = logging.getLogger("sms.worker")

Runner = Callable[..., None]
ReflectRunner = Callable[..., int]

REFLECT_CHECK_INTERVAL_S = 600.0
REFLECT_WINDOW_H = 24
REFLECT_LOOKBACK_DAYS = 7


class Worker:
    def __init__(self, db: Database, storage: PageStorage, settings_store: SettingsStore,
                 runner: Runner = run_mark_job, poll_s: float = 2.0, max_attempts: int = MAX_ATTEMPTS,
                 base_backoff_s: float = 30.0, reflect_runner: ReflectRunner = run_reflect_job):
        self.db = db
        self.storage = storage
        self.settings_store = settings_store
        self.runner = runner
        self.reflect_runner = reflect_runner
        self.poll_s = poll_s
        self.max_attempts = max_attempts
        self.base_backoff_s = base_backoff_s
        self.jobs = JobStore(db)
        self._bucket: Optional[TokenBucket] = None
        self._last_reflect_check: Optional[float] = None  # time.monotonic() of the last scheduler pass

    def _bucket_for(self, rpm: int) -> TokenBucket:
        """One TokenBucket for the worker's lifetime; replaced only when rpm changes.

        Recreating it per job would reset the sliding window each time, so back-to-back
        jobs would never actually be capped at the aggregate rpm_limit.
        """
        if self._bucket is None or self._bucket.rpm != rpm:
            self._bucket = TokenBucket(rpm)
        return self._bucket

    def run_once(self) -> bool:
        job = self.jobs.claim()
        if job is None:
            return False
        try:
            bucket = self._bucket_for(self.settings_store.load().rpm_limit)
            if job["kind"] == "mark":
                self.runner(self.db, self.storage, self.settings_store, job["submission_id"], bucket=bucket)
            elif job["kind"] == "reflect":
                payload = json.loads(job["payload_json"] or "{}")
                lookback = int(payload.get("lookback_days", REFLECT_LOOKBACK_DAYS))
                if payload.get("run_id") is None:
                    # One reflection_runs row per job: created on the first attempt and remembered
                    # in the payload so a retried attempt updates it instead of adding another.
                    payload["run_id"] = open_reflection_run(self.db, payload["subject"], lookback)
                    self.jobs.set_payload(job["id"], payload)
                self.reflect_runner(self.db, self.settings_store, payload["subject"], lookback, bucket=bucket,
                                    run_id=payload["run_id"])
            else:
                raise ValueError(f"unknown job kind {job['kind']!r}")
            self.jobs.finish(job["id"])
        except Exception as e:  # noqa: BLE001 - every failure is recorded on the job
            msg = error_message(e)
            if is_retryable(e) and job["attempts"] < self.max_attempts:
                delay = self.base_backoff_s * (2 ** (job["attempts"] - 1))
                log.warning("job %s retry in %.0fs: %s", job["id"], delay, msg)
                self.jobs.retry_later(job["id"], delay, msg)
            else:
                log.error("job %s failed: %s", job["id"], msg)
                self.jobs.fail(job["id"], msg)
        return True

    def run_forever(self, stop: threading.Event) -> None:
        reset_done = False
        while not stop.is_set():
            try:
                if not reset_done:
                    reset = self.jobs.reset_running()
                    if reset:
                        log.info("re-queued %d interrupted job(s)", reset)
                    reset_done = True
                self.jobs.heartbeat()
                self._maybe_schedule_reflection()
                worked = self.run_once()
            except Exception:  # noqa: BLE001
                log.exception("worker loop error")
                worked = False
            if not worked:
                stop.wait(self.poll_s)

    def _maybe_schedule_reflection(self) -> None:
        """Nightly reflection: at most every 10 minutes, enqueue a reflect job for each subject
        that has teacher corrections in the last 24 h, no reflection run in the last 24 h and no
        reflect job already queued or running."""
        now = time.monotonic()
        if self._last_reflect_check is not None and now - self._last_reflect_check < REFLECT_CHECK_INTERVAL_S:
            return
        self._last_reflect_check = now
        settings = self.settings_store.load()
        if not settings.auto_reflect or not settings.has_key:
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=REFLECT_WINDOW_H)).strftime("%Y-%m-%d %H:%M:%S")
        pending = self.jobs.pending_reflect_subjects()
        for subject in SubjectRouter.KNOWN_SUBJECTS:
            if subject in pending:
                continue
            corrected = self.db.query(
                "SELECT COUNT(*) AS c FROM teacher_corrections tc JOIN marking_runs mr ON mr.run_id = tc.run_id "
                "WHERE mr.subject = :s AND tc.created_at >= :cutoff", {"s": subject, "cutoff": cutoff})[0]["c"]
            if not corrected:
                continue
            # A failed run does not count: it is tried again on the next pass.
            ran = self.db.query("SELECT COUNT(*) AS c FROM reflection_runs WHERE subject = :s AND started_at >= :cutoff "
                                "AND error IS NULL", {"s": subject, "cutoff": cutoff})[0]["c"]
            if ran:
                continue
            if self.jobs.enqueue_unique("reflect", {"subject": subject, "lookback_days": REFLECT_LOOKBACK_DAYS},
                                        dedupe_key=f"reflect:{subject}") is not None:
                log.info("scheduled nightly reflection for %s", subject)

    def start_thread(self, stop: threading.Event) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, args=(stop,), name="sms-worker", daemon=True)
        t.start()
        return t
