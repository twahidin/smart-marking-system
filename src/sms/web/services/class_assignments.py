"""A bank template set to a class: due date, status (draft/open/released), and the students' hand-ins."""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sms.memory.db import Database
from sms.storage import PageStorage
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.assignments import get_template
from sms.web.services.classes import get_class
from sms.web.services.pages_cleanup import unlink_pages
from sms.web.services.submissions import create_submission
from sms.worker.jobs import JobStore

STATUSES = ("draft", "open", "released")

_SELECT = ("SELECT a.*, t.subject AS subject, t.scheme_kind AS scheme_kind, "
           "(SELECT COUNT(*) FROM submissions s WHERE s.class_assignment_id = a.id) AS submission_count, "
           "(SELECT COUNT(*) FROM submissions s WHERE s.class_assignment_id = a.id AND s.status NOT IN ('done', 'needs_you')) AS in_progress "
           "FROM class_assignments a LEFT JOIN assignment_templates t ON t.id = a.template_id")


def _row(r: dict) -> Dict[str, Any]:
    status = r["status"]
    derived = "marking" if status == "open" and int(r["in_progress"] or 0) > 0 else status
    return {
        "id": r["id"], "class_id": r["class_id"], "template_id": r["template_id"], "title": r["title"],
        "due_at": iso_utc(r["due_at"]), "status": status, "derived_status": derived,
        "allow_student_uploads": bool(r["allow_student_uploads"]), "released_at": iso_utc(r["released_at"]),
        "template_deleted": r["subject"] is None, "subject": r["subject"], "scheme_kind": r["scheme_kind"],
        "submission_count": int(r["submission_count"] or 0),
        "created_at": iso_utc(r["created_at"]), "updated_at": iso_utc(r["updated_at"]),
    }


def list_class_assignments(db: Database, class_id: int) -> List[Dict[str, Any]]:
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    return [_row(r) for r in db.query(_SELECT + " WHERE a.class_id = :c ORDER BY a.due_at IS NULL, a.due_at, a.id DESC", {"c": class_id})]


def get_class_assignment(db: Database, class_id: int, caid: int) -> Optional[Dict[str, Any]]:
    rows = db.query(_SELECT + " WHERE a.id = :id AND a.class_id = :c", {"id": caid, "c": class_id})
    return _row(rows[0]) if rows else None


def require_class_assignment(db: Database, class_id: int, caid: int) -> Dict[str, Any]:
    ca = get_class_assignment(db, class_id, caid)
    if ca is None:
        raise ApiError(404, "not_found", "No such assignment in this class")
    return ca


def _parse_due(due_at: Optional[str]) -> Optional[str]:
    """ISO 8601 -> 'YYYY-MM-DD HH:MM:SS' UTC for the DateTime column; None passes through."""
    if not due_at:
        return None
    try:
        dt = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "bad_due", "Due date must be an ISO 8601 date-time")
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def set_assignment(db: Database, class_id: int, *, template_id: int, title: Optional[str] = None,
                   due_at: Optional[str] = None, allow_student_uploads: bool = True) -> Dict[str, Any]:
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    t = get_template(db, template_id)
    if t is None:
        raise ApiError(404, "not_found", "No such assignment in the bank")
    title = (title or "").strip() or t["title"]
    caid = db.insert("INSERT INTO class_assignments (class_id, template_id, title, due_at, allow_student_uploads) "
                     "VALUES (:c, :t, :title, :due, :allow) RETURNING id",
                     {"c": class_id, "t": template_id, "title": title[:200], "due": _parse_due(due_at),
                      "allow": bool(allow_student_uploads)})
    return get_class_assignment(db, class_id, caid)  # type: ignore[return-value]


def update_class_assignment(db: Database, class_id: int, caid: int, *, title: str, due_at: Optional[str],
                            allow_student_uploads: bool, status: str) -> Dict[str, Any]:
    ca = require_class_assignment(db, class_id, caid)
    if status not in STATUSES:
        raise ApiError(400, "bad_status", "Status must be draft, open or released")
    if status == "released" and ca["status"] != "released":
        raise ApiError(400, "bad_status", "Use Release feedback to release an assignment")
    title = (title or "").strip()
    if not title:
        raise ApiError(400, "bad_title", "Give the assignment a title")
    db.execute("UPDATE class_assignments SET title = :title, due_at = :due, allow_student_uploads = :allow, status = :st, "
               "updated_at = CURRENT_TIMESTAMP WHERE id = :id",
               {"title": title[:200], "due": _parse_due(due_at), "allow": bool(allow_student_uploads), "st": status, "id": caid})
    return get_class_assignment(db, class_id, caid)  # type: ignore[return-value]


def delete_class_assignment(db: Database, class_id: int, caid: int) -> None:
    ca = require_class_assignment(db, class_id, caid)
    if ca["submission_count"]:
        raise ApiError(409, "in_use", f"{ca['submission_count']} hand-in(s) reference this assignment — remove them first")
    db.execute("DELETE FROM class_assignments WHERE id = :id", {"id": caid})


def get_student(db: Database, class_id: int, student_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query("SELECT id, class_id, reg_no, name FROM students WHERE id = :s AND class_id = :c",
                    {"s": student_id, "c": class_id})
    return dict(rows[0]) if rows else None


def hand_in(db: Database, storage: PageStorage, jobs: JobStore, *, ca: Dict[str, Any], student: Dict[str, Any],
            files: List[Tuple[str, bytes]], source: str) -> Dict[str, Any]:
    """Create the student's submission for a class assignment; marking starts as for any upload."""
    template = get_template(db, ca["template_id"])
    if template is None:
        raise ApiError(409, "template_deleted", "This assignment was deleted from the bank — set it again from a current assignment")
    if db.query("SELECT 1 FROM submissions WHERE class_assignment_id = :a AND student_id = :s", {"a": ca["id"], "s": student["id"]}):
        raise ApiError(409, "already_handed_in", "This student has already handed in — remove the hand-in first to redo it")
    return create_submission(db, storage, jobs, label=f"#{student['reg_no']} {student['name']}", subject=template["subject"],
                             context=template["context"], rubric_json=json.dumps(template["rubric"]), files=files,
                             assignment_id=template["id"], class_assignment_id=ca["id"], student_id=student["id"], source=source)


def remove_hand_in(db: Database, storage: PageStorage, ca_id: int, student_id: int) -> None:
    """Delete the student's submission (pages, jobs, queue items) so they can hand in again."""
    rows = db.query("SELECT id FROM submissions WHERE class_assignment_id = :a AND student_id = :s", {"a": ca_id, "s": student_id})
    if not rows:
        raise ApiError(404, "not_found", "This student has not handed in")
    sid = rows[0]["id"]
    if db.query("SELECT 1 FROM jobs WHERE submission_id = :s AND status = 'running'", {"s": sid}):
        raise ApiError(409, "marking", "This script is being marked right now — try again in a minute")
    with db.transaction() as tx:
        paths = [r["storage_path"] for r in tx.query("SELECT storage_path FROM pages WHERE submission_id = :s AND deleted_at IS NULL", {"s": sid})]
        tx.execute("DELETE FROM teacher_queue WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM jobs WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM submissions WHERE id = :s", {"s": sid})
        # Files are content-addressed: only unlink what no other undeleted page still references
        # (another script with the same page, a question paper) — same rule as pages_cleanup.
        orphaned = [p for p in dict.fromkeys(paths)
                    if not tx.query("SELECT 1 FROM pages WHERE storage_path = :p AND deleted_at IS NULL", {"p": p})]
    unlink_pages(storage, orphaned)
