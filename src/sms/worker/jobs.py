import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from sms.memory.db import Database
from sms.timeutil import iso_utc

MAX_ATTEMPTS = 5


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _in(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")


class JobStore:
    def __init__(self, db: Database):
        self.db = db

    def enqueue(self, kind: str, submission_id: Optional[int] = None, payload: Optional[dict] = None) -> int:
        job_id = self.db.insert(
            "INSERT INTO jobs (kind, submission_id, status, payload_json) VALUES (:k, :s, 'queued', :p) RETURNING id",
            {"k": kind, "s": submission_id, "p": json.dumps(payload) if payload is not None else None},
        )
        if submission_id is not None:
            self.db.execute("UPDATE submissions SET status = 'queued', updated_at = CURRENT_TIMESTAMP WHERE id = :s",
                            {"s": submission_id})
        return job_id

    def claim(self) -> Optional[dict]:
        now = _now()
        with self.db.transaction() as tx:
            lock = " FOR UPDATE SKIP LOCKED" if not self.db.is_sqlite else ""
            rows = tx.query(
                "SELECT id FROM jobs WHERE status = 'queued' AND (not_before IS NULL OR not_before <= :now) "
                f"ORDER BY created_at, id LIMIT 1{lock}",
                {"now": now},
            )
            if not rows:
                return None
            job_id = rows[0]["id"]
            changed = tx.execute(
                "UPDATE jobs SET status = 'running', started_at = :now, attempts = attempts + 1, error = NULL "
                "WHERE id = :id AND status = 'queued'",
                {"now": now, "id": job_id},
            )
            if changed != 1:
                return None
            tx.execute(
                "UPDATE submissions SET status = 'marking', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = (SELECT submission_id FROM jobs WHERE id = :id)",
                {"id": job_id},
            )
            return tx.query("SELECT * FROM jobs WHERE id = :id", {"id": job_id})[0]

    def finish(self, job_id: int) -> None:
        self.db.execute("UPDATE jobs SET status = 'done', finished_at = :now WHERE id = :id",
                        {"now": _now(), "id": job_id})

    def retry_later(self, job_id: int, delay_s: float, error: str) -> None:
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE jobs SET status = 'queued', not_before = :nb, error = :err WHERE id = :id",
                {"nb": _in(delay_s), "err": error, "id": job_id},
            )
            tx.execute(
                "UPDATE submissions SET status = 'queued', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = (SELECT submission_id FROM jobs WHERE id = :id)",
                {"id": job_id},
            )

    def fail(self, job_id: int, error: str) -> None:
        with self.db.transaction() as tx:
            tx.execute("UPDATE jobs SET status = 'failed', finished_at = :now, error = :err WHERE id = :id",
                       {"now": _now(), "err": error, "id": job_id})
            tx.execute(
                "UPDATE submissions SET status = 'failed', updated_at = CURRENT_TIMESTAMP "
                "WHERE id = (SELECT submission_id FROM jobs WHERE id = :id)",
                {"id": job_id},
            )

    def reset_running(self) -> int:
        with self.db.transaction() as tx:
            tx.execute(
                "UPDATE submissions SET status = 'queued' WHERE id IN "
                "(SELECT submission_id FROM jobs WHERE status = 'running' AND submission_id IS NOT NULL)"
            )
            return tx.execute("UPDATE jobs SET status = 'queued', started_at = NULL WHERE status = 'running'")

    def heartbeat(self) -> None:
        now = _now()
        if self.db.execute("UPDATE worker_heartbeat SET last_seen = :now WHERE id = 1", {"now": now}) == 0:
            self.db.execute("INSERT INTO worker_heartbeat (id, last_seen) VALUES (1, :now)", {"now": now})

    def last_heartbeat(self) -> Optional[str]:
        rows = self.db.query("SELECT last_seen FROM worker_heartbeat WHERE id = 1")
        return iso_utc(rows[0]["last_seen"]) if rows else None

    def pending_reflect_subjects(self) -> Set[str]:
        """Subjects with a queued or running reflect job."""
        rows = self.db.query("SELECT payload_json FROM jobs WHERE kind = 'reflect' AND status IN ('queued', 'running')")
        out: Set[str] = set()
        for r in rows:
            payload = json.loads(r["payload_json"]) if r["payload_json"] else {}
            if payload.get("subject"):
                out.add(payload["subject"])
        return out

    def job_for_submission(self, submission_id: int) -> Optional[dict]:
        rows = self.db.query("SELECT * FROM jobs WHERE submission_id = :s ORDER BY id DESC LIMIT 1",
                             {"s": submission_id})
        return rows[0] if rows else None
