"""What a student can see: their class, their assignments, their own hand-in and released feedback."""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sms.memory.db import Database
from sms.schemas.scheme import norm_qid
from sms.storage import PageStorage
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.class_assignments import get_class_assignment, get_student, hand_in
from sms.web.services.classes import normalise_code
from sms.web.services.submissions import get_submission
from sms.worker.jobs import JobStore

NO_CLASS = "That class code is not right — check the link your teacher shared"


def lookup_student(db: Database, code: str, reg_no: int) -> Dict[str, Any]:
    code = normalise_code(code)
    rows = db.query("SELECT id, name, code FROM classes WHERE code = :c AND archived_at IS NULL", {"c": code})
    if not rows:
        raise ApiError(404, "no_such_class", NO_CLASS)
    cls = rows[0]
    st = db.query("SELECT id, name, reg_no FROM students WHERE class_id = :c AND reg_no = :r", {"c": cls["id"], "r": reg_no})
    if not st:
        raise ApiError(404, "no_such_student", f"No student #{reg_no} in this class — check the number on your class list")
    return {"class_id": cls["id"], "class_name": cls["name"], "code": cls["code"],
            "student_id": st[0]["id"], "student_name": st[0]["name"], "reg_no": int(st[0]["reg_no"])}


def touch_last_seen(db: Database, student_id: int) -> None:
    db.execute("UPDATE students SET last_seen_at = CURRENT_TIMESTAMP WHERE id = :s", {"s": student_id})


def public(found: Dict[str, Any]) -> Dict[str, Any]:
    return {"class_name": found["class_name"], "code": found["code"], "student_name": found["student_name"], "reg_no": found["reg_no"]}


# --- assignments, hand-in, released feedback, own pages ---------------------------------------

def _status(sub: Optional[dict], released: bool) -> str:
    """The student's view of progress: nothing handed in, handed in (marking not finished), checking
    (marked but the teacher has not released, or a part is still with the teacher), or feedback ready."""
    if sub is None:
        return "to_hand_in"
    if sub["status"] not in ("done", "needs_you"):
        return "handed_in"
    if sub["status"] == "needs_you" or not released:
        return "checking"
    return "feedback_ready"


def _visible(db: Database, student: dict, caid: Optional[int] = None) -> List[dict]:
    """The class's non-draft assignments joined with this student's own hand-in (if any)."""
    sql = ("SELECT a.*, s.id AS submission_id, s.status AS sub_status, s.handed_in_at, s.run_id, "
           "(SELECT COUNT(*) FROM pages p WHERE p.submission_id = s.id) AS page_count "
           "FROM class_assignments a LEFT JOIN submissions s ON s.class_assignment_id = a.id AND s.student_id = :st "
           "WHERE a.class_id = :c AND a.status != 'draft'")
    params: Dict[str, Any] = {"st": student["student_id"], "c": student["class_id"]}
    if caid is not None:
        sql += " AND a.id = :a"
        params["a"] = caid
    return db.query(sql + " ORDER BY a.due_at IS NULL, a.due_at, a.id DESC", params)


def _row(r: dict) -> Dict[str, Any]:
    sub = {"status": r["sub_status"]} if r["submission_id"] is not None else None
    return {"id": r["id"], "title": r["title"], "due_at": iso_utc(r["due_at"]),
            "status": _status(sub, r["status"] == "released"), "handed_in_at": iso_utc(r["handed_in_at"]),
            "pages": int(r["page_count"] or 0), "allow_student_uploads": bool(r["allow_student_uploads"])}


def student_assignments(db: Database, student: dict) -> List[Dict[str, Any]]:
    return [_row(r) for r in _visible(db, student)]


def feedback_view(detail: dict) -> Dict[str, Any]:
    """The student-safe projection of a marked submission: final marks per question, comments, transcription.
    Nothing about escalation, confidence or the reviewer stage leaves here."""
    fb = detail.get("feedback") or {}
    comments = {norm_qid(c.get("q_id")): c for c in fb.get("per_question_comments") or []}
    questions = []
    if detail.get("marks_version") == 2:
        for p in detail.get("parts") or []:
            c = comments.get(norm_qid(p["q_id"]), {})
            questions.append({"label": p["label"], "mark": p["teacher"]["total"] if p.get("teacher") else p["total"], "max": p["max"],
                              "comment": c.get("comment", ""), "try_next": c.get("suggested_action", ""),
                              "transcription": p.get("extracted") or ""})
    else:
        for m in detail.get("marks") or []:
            c = comments.get(norm_qid(m["q_id"]), {})
            questions.append({"label": m["q_id"], "mark": sum(m["teacher_scores"]) if m.get("teacher_scores") else m["total"], "max": m["max"],
                              "comment": c.get("comment", ""), "try_next": c.get("suggested_action", ""),
                              "transcription": m.get("evidence") or ""})
    totals = detail.get("totals") or {}
    return {"summary": fb.get("summary", ""), "strengths": fb.get("strengths") or [],
            "improvement_plan": fb.get("improvement_plan") or [], "next_steps": fb.get("next_steps") or [],
            "total": totals.get("total"), "max": totals.get("total_max"), "questions": questions,
            "pages": [p["id"] for p in detail.get("pages") or [] if not p["deleted"]]}


def student_assignment(db: Database, jobs: JobStore, student: dict, caid: int) -> Dict[str, Any]:
    rows = _visible(db, student, caid)
    if not rows:
        raise ApiError(404, "not_found", "No such assignment")
    r = rows[0]
    out = _row(r)
    out["feedback"] = None
    if out["status"] == "feedback_ready":
        detail = get_submission(db, jobs, r["submission_id"])
        out["feedback"] = feedback_view(detail) if detail else None
    return out


_HAND_IN_MESSAGES = {
    "already_handed_in": "You have already handed this in — ask your teacher if you need to hand in again",
    "template_deleted": "This assignment is no longer available — ask your teacher",
}


def student_hand_in(db: Database, storage: PageStorage, jobs: JobStore, student: dict, caid: int,
                    files: List[Tuple[str, bytes]]) -> Dict[str, Any]:
    ca = get_class_assignment(db, student["class_id"], caid)
    if ca is None or ca["status"] == "draft":
        raise ApiError(404, "not_found", "No such assignment")
    if ca["status"] != "open" or not ca["allow_student_uploads"]:
        raise ApiError(403, "uploads_closed", "Hand-ins are closed for this assignment — ask your teacher")
    st = get_student(db, student["class_id"], student["student_id"])
    if st is None:
        raise ApiError(401, "student_session", "Enter your class code and number to continue")
    try:
        return hand_in(db, storage, jobs, ca=ca, student=st, files=files, source="student")
    except ApiError as e:
        # Same codes as the teacher's route, but say what a student can do about it.
        if e.code in _HAND_IN_MESSAGES:
            raise ApiError(e.status, e.code, _HAND_IN_MESSAGES[e.code]) from None
        raise


def student_page_path(db: Database, storage: PageStorage, student: dict, page_id: int) -> Path:
    """A page image of the student's own hand-in; anyone else's page is simply not found."""
    rows = db.query("SELECT p.storage_path, p.deleted_at FROM pages p JOIN submissions s ON s.id = p.submission_id "
                    "WHERE p.id = :p AND s.student_id = :st AND p.kind = 'student'", {"p": page_id, "st": student["student_id"]})
    if not rows:
        raise ApiError(404, "not_found", "No such page")
    if rows[0]["deleted_at"] is not None:
        raise ApiError(410, "gone", "This page was deleted after marking")
    path = storage.abs(rows[0]["storage_path"])
    if not path.is_file():
        raise ApiError(404, "not_found", "Page image is missing from storage")
    return path
