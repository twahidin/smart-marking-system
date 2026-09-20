"""A bank template set to a class: due date, status (draft/open/released), and the students' hand-ins."""
import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sms.memory.db import Database
from sms.schemas.scheme import q_label
from sms.storage import PageStorage
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.assignments import get_template
from sms.web.services.classes import get_class
from sms.web.services.pages_cleanup import unlink_pages
from sms.web.services.submissions import create_submission, get_submission, row_key, row_max, submission_totals
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
    if ca["status"] == "released" and status != "released":
        raise ApiError(400, "bad_status", "A released assignment cannot be reopened")
    if ca["status"] == "open" and status == "draft" and ca["submission_count"]:
        raise ApiError(400, "bad_status", "Remove the hand-ins before moving it back to draft")
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
            files: List[Tuple[str, bytes]], source: str, max_pages: Optional[int] = None) -> Dict[str, Any]:
    """Create the student's submission for a class assignment; marking starts as for any upload.
    `max_pages` (pages after PDF rasterising) tightens the default per-script limit for student hand-ins."""
    template = get_template(db, ca["template_id"])
    if template is None:
        raise ApiError(409, "template_deleted", "This assignment was deleted from the bank — set it again from a current assignment")
    if db.query("SELECT 1 FROM submissions WHERE class_assignment_id = :a AND student_id = :s", {"a": ca["id"], "s": student["id"]}):
        raise ApiError(409, "already_handed_in", "This student has already handed in — remove the hand-in first to redo it")
    return create_submission(db, storage, jobs, label=f"#{student['reg_no']} {student['name']}", subject=template["subject"],
                             context=template["context"], rubric_json=json.dumps(template["rubric"]), files=files,
                             assignment_id=template["id"], class_assignment_id=ca["id"], student_id=student["id"], source=source,
                             max_pages=max_pages)


def _unsent_hand_in_ids(tx, ca_id: int, student_id: int) -> List[int]:
    """The outbox rows still waiting to announce this student's hand-in on this assignment.

    The student id lives inside `payload_json`, and SQLite and Postgres spell reaching into JSON
    differently, so the (few, unsent, single-assignment) rows are filtered here instead."""
    rows = tx.query("SELECT id, payload_json FROM notifications WHERE kind = 'hand_in' "
                    "AND sent_at IS NULL AND class_assignment_id = :a", {"a": ca_id})
    out = []
    for r in rows:
        try:
            payload = json.loads(r["payload_json"] or "{}")
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("student_id") == student_id:
            out.append(int(r["id"]))
    return out


def remove_hand_in(db: Database, storage: PageStorage, ca_id: int, student_id: int) -> None:
    """Delete the student's submission (pages, jobs, queue items, marking runs) so they can hand in again.

    An announcement that has not gone out yet goes with it: a hand-in the teacher has already undone
    is not news, and the message would name a script that no longer exists."""
    rows = db.query("SELECT id FROM submissions WHERE class_assignment_id = :a AND student_id = :s", {"a": ca_id, "s": student_id})
    if not rows:
        raise ApiError(404, "not_found", "This student has not handed in")
    sid = rows[0]["id"]
    if db.query("SELECT 1 FROM jobs WHERE submission_id = :s AND status = 'running'", {"s": sid}):
        raise ApiError(409, "marking", "This script is being marked right now — try again in a minute")
    with db.transaction() as tx:
        paths = [r["storage_path"] for r in tx.query("SELECT storage_path FROM pages WHERE submission_id = :s AND deleted_at IS NULL", {"s": sid})]
        file_paths = [r["stored_path"] for r in tx.query("SELECT stored_path FROM submission_files WHERE submission_id = :s "
                                                         "AND deleted_at IS NULL", {"s": sid})]
        tx.execute("DELETE FROM teacher_queue WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM marking_runs WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM jobs WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM pages WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM submission_files WHERE submission_id = :s", {"s": sid})
        tx.execute("DELETE FROM submissions WHERE id = :s", {"s": sid})
        stale = _unsent_hand_in_ids(tx, ca_id, student_id)
        if stale:
            clause = ", ".join(f":n{i}" for i in range(len(stale)))
            tx.execute(f"DELETE FROM notifications WHERE id IN ({clause})",
                       {f"n{i}": n for i, n in enumerate(stale)})
        # Files are content-addressed: only unlink what no other undeleted page still references
        # (another script with the same page, a question paper) — same rule as pages_cleanup.
        orphaned = [p for p in dict.fromkeys(paths)
                    if not tx.query("SELECT 1 FROM pages WHERE storage_path = :p AND deleted_at IS NULL", {"p": p})]
        orphaned += [p for p in dict.fromkeys(file_paths)
                     if not tx.query("SELECT 1 FROM submission_files WHERE stored_path = :p AND deleted_at IS NULL", {"p": p})]
    unlink_pages(storage, orphaned)


# --- roster, release and marks export ---------------------------------------------------------

def _student_status(sub: Optional[dict], released: bool) -> str:
    if sub is None:
        return "not_handed_in"
    st = sub["status"]
    if st in ("uploaded", "queued"):
        return "handed_in"
    if st == "marking":
        return "marking"
    if st == "failed":
        return "failed"
    if st == "needs_you":
        return "needs_you"
    return "released" if released else "ready"


def roster(db: Database, ca: Dict[str, Any]) -> Dict[str, Any]:
    """One row per student in the class (register order) with their hand-in's progress and totals,
    plus progress counts. `failed` scripts count under `marking` and `released` under `ready`."""
    students = db.query("SELECT id, reg_no, name FROM students WHERE class_id = :c ORDER BY reg_no", {"c": ca["class_id"]})
    subs = {r["student_id"]: r for r in db.query(
        "SELECT s.*, (SELECT COUNT(*) FROM pages p WHERE p.submission_id = s.id) AS page_count "
        "FROM submissions s WHERE s.class_assignment_id = :a", {"a": ca["id"]})}
    pending: Dict[int, List[str]] = {}
    for q in db.query("SELECT q.submission_id, q.q_id FROM teacher_queue q JOIN submissions s ON s.id = q.submission_id "
                      "WHERE s.class_assignment_id = :a AND q.status = 'pending' ORDER BY q.id", {"a": ca["id"]}):
        pending.setdefault(q["submission_id"], []).append(q_label(q["q_id"]))
    released = ca["status"] == "released"
    due = ca["due_at"]
    rows = []
    counts = {"not_handed_in": 0, "handed_in": 0, "marking": 0, "needs_you": 0, "ready": 0}
    for st in students:
        sub = subs.get(st["id"])
        status = _student_status(sub, released)
        totals = submission_totals(db, sub) if sub else None
        handed = iso_utc(sub["handed_in_at"]) if sub else None
        rows.append({
            "student_id": st["id"], "reg_no": int(st["reg_no"]), "name": st["name"],
            "submission_id": sub["id"] if sub else None, "pages": int(sub["page_count"] or 0) if sub else 0,
            "handed_in_at": handed, "late": bool(due and handed and handed > due), "source": sub["source"] if sub else None,
            "status": status,
            "total": totals["total"] if totals else None, "total_upper": totals["total_upper"] if totals else None,
            "total_max": totals["total_max"] if totals else None,
            "needs_you_parts": pending.get(sub["id"], []) if sub else [],
        })
        bucket = {"failed": "marking", "released": "ready"}.get(status, status)
        counts[bucket] += 1
    return {"rows": rows, "counts": counts}


def release(db: Database, class_id: int, caid: int) -> Dict[str, Any]:
    """Release feedback to the class: only an open assignment, and refused while any part still waits
    in the review queue or nothing has been marked. Releasing is one-way (see update_class_assignment)."""
    ca = require_class_assignment(db, class_id, caid)
    if ca["status"] == "released":
        raise ApiError(409, "already_released", "Feedback for this assignment has already been released")
    if ca["status"] != "open":
        raise ApiError(409, "not_open", "Open the assignment before releasing feedback")
    n = int(db.query("SELECT COUNT(*) AS c FROM teacher_queue q JOIN submissions s ON s.id = q.submission_id "
                     "WHERE s.class_assignment_id = :a AND q.status = 'pending'", {"a": caid})[0]["c"] or 0)
    if n:
        raise ApiError(409, "needs_you", f"{n} part{'s' if n != 1 else ''} still need{'s' if n == 1 else ''} you — clear the review queue first")
    marked = db.query("SELECT COUNT(*) AS c FROM submissions WHERE class_assignment_id = :a AND run_id IS NOT NULL", {"a": caid})[0]["c"]
    if not int(marked or 0):
        raise ApiError(409, "nothing_marked", "Nothing has been marked yet")
    db.execute("UPDATE class_assignments SET status = 'released', released_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
               "WHERE id = :id", {"id": caid})
    # Releasing is the moment the class set is final, so the teacher's insights are generated then.
    # Imported here: the job module reads assignments through this one, so a top-level import cycles.
    from sms.worker.insights_job import enqueue_insights
    enqueue_insights(JobStore(db), caid)
    return get_class_assignment(db, class_id, caid)  # type: ignore[return-value]


def part_columns(template: dict, marks: Iterable[Dict[str, Any]]) -> List[Tuple[str, str, int]]:
    """(key, label, max) per CSV column. A mark scheme / rubric template has one column per scheme row
    in scheme order. A criteria template has no per-question scheme, so its columns are the questions
    the marked scripts answered (`marks`: one key -> mark dict per script, from final_mark_by_key) in
    first-seen order, each worth the rubric's total (the sum of its criterion maxima)."""
    kind = template["scheme_kind"]
    if kind in ("mark_scheme", "rubric"):
        seen: Set[str] = set()
        cols = []
        for row in template["scheme"]:
            key = row_key(kind, row)
            if key not in seen:
                seen.add(key)
                cols.append((key, q_label(key) if kind == "mark_scheme" else key, row_max(kind, row)))
        return cols
    per_q_max = sum(int(c["max_score"]) for c in template["rubric"]["criterion_defs"])
    keys = list(dict.fromkeys(k for m in marks for k in m))
    return [(k, q_label(k), per_q_max) for k in keys]


def final_mark_by_key(detail: dict) -> Dict[str, Any]:
    """key -> int mark or "Review" (pending) from a submission detail; teacher corrections win."""
    out: Dict[str, Any] = {}
    if detail.get("marks_version") == 2:
        for p in detail.get("parts") or []:
            out[p["q_id"]] = "Review" if p["escalated"] else (p["teacher"]["total"] if p.get("teacher") else p["total"])
    else:
        for m in detail.get("marks") or []:
            out[m["q_id"]] = "Review" if m["escalated"] else (sum(m["teacher_scores"]) if m.get("teacher_scores") else m["total"])
    return out


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "assignment"


def marks_csv(db: Database, jobs: JobStore, ca: Dict[str, Any]) -> str:
    """One row per student: a column per part (see part_columns), total, max and status; blanks for
    students who have not handed in or whose script is not marked yet (their `max` is the sum of the
    column maxima)."""
    template = get_template(db, ca["template_id"])
    if template is None:
        raise ApiError(409, "template_deleted", "This assignment was deleted from the bank — the marks CSV needs its scheme")
    rows = roster(db, ca)["rows"]
    marks_by_sub: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        if r["submission_id"] is not None:
            detail = get_submission(db, jobs, r["submission_id"])
            marks_by_sub[r["submission_id"]] = final_mark_by_key(detail) if detail and detail.get("run_id") else {}
    cols = part_columns(template, marks_by_sub.values())
    scheme_max = sum(m for _, _, m in cols)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["reg_no", "name", *[label for _, label, _ in cols], "total", "max", "status"])
    for r in rows:
        marks = marks_by_sub.get(r["submission_id"], {})
        cells = [marks.get(k, "") for k, _, _ in cols]
        total = "" if r["total"] is None else r["total"]
        maximum = r["total_max"] if r["total_max"] is not None else scheme_max
        w.writerow([r["reg_no"], r["name"], *cells, total, maximum, r["status"]])
    return buf.getvalue()
