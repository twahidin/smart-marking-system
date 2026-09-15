"""Deleting a script's uploaded pages once it is done.

A submission's student pages are deleted when it reaches `done` — marking finished with nothing to
review, or the teacher resolved the last escalated part — if the assignment's "delete pages after
marking" setting (or, when unset / a quick-mark script, the global default in Settings) is on. The
`pages` rows stay, with `deleted_at` set, so the detail still lists them and the page route can answer
410; the file goes only when no other undeleted row (another script with the same page, a question
paper, a scheme) still references the same content-addressed path. Question-paper and scheme pages
are never deleted here.

The DB step and the file step are separate on purpose: callers that already hold a transaction
(`resolve_queue_item`) mark the rows inside it and unlink after commit, so a rolled-back resolve never
loses a file.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from sms.memory.db import Database
from sms.storage import PageStorage
from sms.web.services.assignments import global_delete_pages_default

log = logging.getLogger("sms.pages_cleanup")


def effective_delete_pages(exe, submission_id: int) -> bool:
    """The assignment's `delete_pages_after_marking` when the submission has one and it is set;
    otherwise the global default. `exe` is a Database or a transaction executor."""
    rows = exe.query("SELECT t.delete_pages_after_marking AS flag FROM submissions s "
                     "JOIN assignment_templates t ON t.id = s.assignment_id WHERE s.id = :id", {"id": submission_id})
    if rows and rows[0]["flag"] is not None:
        return bool(rows[0]["flag"])
    return global_delete_pages_default(exe)


def mark_pages_deleted(tx, submission_id: int) -> List[str]:
    """Set `deleted_at` on the submission's undeleted student pages (inside the caller's transaction)
    and return the storage paths that no undeleted row references any more — the files to unlink
    once the transaction has committed. Does not consult the delete flag."""
    rows = tx.query("SELECT id, storage_path FROM pages WHERE submission_id = :s AND kind = 'student' "
                    "AND deleted_at IS NULL ORDER BY page_index", {"s": submission_id})
    if not rows:
        return []
    tx.execute("UPDATE pages SET deleted_at = CURRENT_TIMESTAMP WHERE submission_id = :s AND kind = 'student' "
               "AND deleted_at IS NULL", {"s": submission_id})
    unreferenced: List[str] = []
    for path in dict.fromkeys(r["storage_path"] for r in rows):
        still = tx.query("SELECT COUNT(*) AS c FROM pages WHERE storage_path = :p AND deleted_at IS NULL", {"p": path})[0]["c"]
        if not still:
            unreferenced.append(path)
    return unreferenced


def unlink_pages(storage: PageStorage, paths: List[str]) -> None:
    """Remove the given page files; a missing file is fine, any other OS error is logged (the rows are
    already marked deleted, so the page is gone for the app either way)."""
    for rel in paths:
        try:
            storage.abs(rel).unlink(missing_ok=True)
        except OSError as e:
            log.warning("could not remove page file %s: %s", rel, e)


def delete_submission_pages(db: Database, storage: PageStorage, submission_id: int) -> int:
    """Delete the student pages of a submission if its effective delete flag is on. Returns the number
    of pages marked deleted (0 when the flag is off or nothing is left to delete)."""
    if not effective_delete_pages(db, submission_id):
        return 0
    with db.transaction() as tx:
        before = tx.query("SELECT COUNT(*) AS c FROM pages WHERE submission_id = :s AND kind = 'student' AND deleted_at IS NULL",
                          {"s": submission_id})[0]["c"]
        paths = mark_pages_deleted(tx, submission_id)
    unlink_pages(storage, paths)
    return int(before)


def sweep_done_submissions(db: Database, storage: PageStorage, older_than_hours: int = 24) -> int:
    """Safety net for an inline deletion that failed: delete the pages of every `done` submission last
    updated more than `older_than_hours` ago that still has undeleted student pages (and whose effective
    flag is on). Returns the number of submissions whose pages were deleted."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.query("SELECT DISTINCT s.id FROM submissions s JOIN pages p ON p.submission_id = s.id "
                    "WHERE s.status = 'done' AND s.updated_at < :cutoff AND p.kind = 'student' AND p.deleted_at IS NULL "
                    "ORDER BY s.id", {"cutoff": cutoff})
    swept = 0
    for r in rows:
        try:
            if delete_submission_pages(db, storage, r["id"]):
                swept += 1
        except Exception:  # noqa: BLE001 - one bad script must not stop the sweep
            log.exception("page sweep failed for submission %s", r["id"])
    if swept:
        log.info("page sweep: deleted the pages of %d done script(s)", swept)
    return swept
