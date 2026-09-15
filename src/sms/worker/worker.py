import logging
import threading
import time
from typing import Callable

from sms.memory.db import Database
from sms.providers.errors import error_message, is_retryable
from sms.providers.settings import SettingsStore
from sms.storage import PageStorage
from sms.worker.jobs import MAX_ATTEMPTS, JobStore
from sms.worker.mark_job import run_mark_job

log = logging.getLogger("sms.worker")

Runner = Callable[[Database, PageStorage, SettingsStore, int], None]


class Worker:
    def __init__(self, db: Database, storage: PageStorage, settings_store: SettingsStore,
                 runner: Runner = run_mark_job, poll_s: float = 2.0, max_attempts: int = MAX_ATTEMPTS,
                 base_backoff_s: float = 30.0):
        self.db = db
        self.storage = storage
        self.settings_store = settings_store
        self.runner = runner
        self.poll_s = poll_s
        self.max_attempts = max_attempts
        self.base_backoff_s = base_backoff_s
        self.jobs = JobStore(db)

    def run_once(self) -> bool:
        job = self.jobs.claim()
        if job is None:
            return False
        try:
            if job["kind"] != "mark":
                raise ValueError(f"unknown job kind {job['kind']!r}")
            self.runner(self.db, self.storage, self.settings_store, job["submission_id"])
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
        reset = self.jobs.reset_running()
        if reset:
            log.info("re-queued %d interrupted job(s)", reset)
        while not stop.is_set():
            try:
                self.jobs.heartbeat()
                worked = self.run_once()
            except Exception:  # noqa: BLE001
                log.exception("worker loop error")
                worked = False
            if not worked:
                stop.wait(self.poll_s)

    def start_thread(self, stop: threading.Event) -> threading.Thread:
        t = threading.Thread(target=self.run_forever, args=(stop,), name="sms-worker", daemon=True)
        t.start()
        return t
