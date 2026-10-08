"""Writes the pipeline's stage events to marking_events and keeps submissions.stage current. Every
database error is logged and swallowed: the room going quiet is acceptable, a lost mark is not."""
import logging

from sms.memory.db import Database
from sms.pipeline.events import StageEvent

log = logging.getLogger(__name__)


class EventRecorder:
    def __init__(self, db: Database, submission_id: int):
        self.db = db
        self.submission_id = submission_id

    def emit(self, event: StageEvent) -> None:
        try:
            self.db.execute(
                "INSERT INTO marking_events (submission_id, stage, kind, q_id, note) VALUES (:s, :st, :k, :q, :n)",
                {"s": self.submission_id, "st": event.stage, "k": event.kind, "q": event.q_id, "n": event.note},
            )
            if event.kind == "started" or (event.stage == "done" and event.kind == "finished"):
                self.db.execute("UPDATE submissions SET stage = :st WHERE id = :s",
                                {"st": event.stage, "s": self.submission_id})
        except Exception:  # noqa: BLE001
            log.exception("could not record stage event %s/%s for submission %s", event.stage, event.kind, self.submission_id)
