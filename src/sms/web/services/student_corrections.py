"""Reflect and correct: after feedback is released, a student has a window (reflect_days) to send one
correction per part that lost marks. The AI re-marks it (sms.worker.remark_job); the teacher accepts,
overrides or rejects; releasing makes the new mark visible. Never confuse with teacher_corrections,
which are the teacher's own Review decisions."""
import io
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from sms.memory.db import Database
from sms.schemas.scheme import norm_qid
from sms.storage import PageStorage
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.class_assignments import effective_reflect_days
from sms.worker.jobs import JobStore

REASONS = ("sign", "method", "rushed", "misread", "other")
STATUS_WORDS = {"submitted": "sent", "remarked": "waiting for the teacher", "accepted": "waiting for the teacher",
                "overridden": "waiting for the teacher", "released": "released", "rejected": "rejected"}
FINAL = ("released", "rejected")


def _utcnow() -> datetime:
    """Naive UTC now, like the DB's timestamps (datetime.utcnow() is deprecated)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse(ts) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)


def window_end(db: Database, ca: Dict[str, Any]) -> Optional[datetime]:
    released = _parse(ca.get("released_at"))
    days = effective_reflect_days(db, ca)
    if released is None or days <= 0:
        return None
    return released + timedelta(days=days)


def window_open(db: Database, ca: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    end = window_end(db, ca)
    return end is not None and (now or _utcnow()) < end


def _mark_of(p: dict) -> float:
    return float(p["teacher"]["total"]) if p.get("teacher") else float(p["total"])


def correctable_parts(detail: dict) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for p in detail.get("parts") or []:
        mark, mx = _mark_of(p), float(p["max"])
        if mark < mx:
            out[norm_qid(p["q_id"])] = {"label": p["label"], "mark": mark, "max": mx, "q_id": p["q_id"]}
    return out


def _row(r: dict) -> Dict[str, Any]:
    return {**r, "submitted_at": iso_utc(r.get("submitted_at")), "released_at": iso_utc(r.get("released_at")),
            "created_at": iso_utc(r.get("created_at"))}


def _jpeg(photo: Tuple[str, bytes]) -> bytes:
    try:
        im = Image.open(io.BytesIO(photo[1])).convert("RGB")
    except Exception as e:  # noqa: BLE001
        raise ApiError(400, "bad_photo", "That photo could not be read — try a JPG or PNG") from e
    im.thumbnail((2000, 2000))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def submit_correction(db: Database, storage: PageStorage, jobs: JobStore, *, ca: Dict[str, Any], submission_detail: dict,
                      q_id: str, reason: str, text: Optional[str], photo: Optional[Tuple[str, bytes]]) -> Dict[str, Any]:
    if not window_open(db, ca):
        raise ApiError(409, "window_closed", "The reflection window for this assignment has closed")
    parts = correctable_parts(submission_detail)
    key = norm_qid(q_id)
    if key not in parts:
        raise ApiError(400, "not_correctable", "That part has full marks or does not exist")
    text = (text or "").strip()
    if not text and photo is None:
        raise ApiError(400, "empty_correction", "Type your corrected working or add a photo")
    sid = submission_detail["id"]
    if db.query("SELECT 1 FROM student_corrections WHERE submission_id = :s AND q_id = :q", {"s": sid, "q": key}):
        raise ApiError(409, "already_corrected", "You have already sent a correction for this part")
    page_id = None
    if photo is not None:
        data = _jpeg(photo)
        digest, rel = storage.put_jpeg(data)
        n = db.query("SELECT COUNT(*) AS c FROM pages WHERE submission_id = :s", {"s": sid})[0]["c"]
        page_id = db.insert("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height, kind) "
                            "VALUES (:s, :i, :d, :p, 0, 0, 'correction') RETURNING id",
                            {"s": sid, "i": 1000 + int(n), "d": digest, "p": rel})
    cid = db.insert("INSERT INTO student_corrections (submission_id, q_id, reason, text, page_id, status) "
                    "VALUES (:s, :q, :r, :t, :p, 'submitted') RETURNING id",
                    {"s": sid, "q": key, "r": reason if reason in REASONS else "other", "t": text or None, "p": page_id})
    jobs.enqueue("remark", payload={"correction_id": cid})
    return _row(db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": cid})[0])


def list_corrections(db: Database, class_assignment_id: int) -> List[Dict[str, Any]]:
    rows = db.query("SELECT c.*, s.label AS submission_label, st.reg_no AS reg_no, st.name AS student_name "
                    "FROM student_corrections c JOIN submissions s ON s.id = c.submission_id "
                    "LEFT JOIN students st ON st.id = s.student_id WHERE s.class_assignment_id = :ca ORDER BY c.id", {"ca": class_assignment_id})
    return [_row(r) for r in rows]


def decide(db: Database, correction_id: int, action: str, *, total: Optional[float] = None, reason: str = "") -> Dict[str, Any]:
    rows = db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": correction_id})
    if not rows:
        raise ApiError(404, "not_found", "No such correction")
    r = rows[0]
    if r["status"] in FINAL:
        raise ApiError(409, "final", "This correction has already been released or rejected")
    if action == "accept":
        if r["remark_total"] is None:
            raise ApiError(409, "not_remarked", "The Marker has not re-marked this yet — override it instead")
        db.execute("UPDATE student_corrections SET status = 'accepted', teacher_total = NULL WHERE id = :id", {"id": correction_id})
    elif action == "override":
        mx = r["remark_max"]
        if total is None or total < 0 or (mx is not None and total > float(mx)):
            raise ApiError(400, "bad_total", f"Mark must be between 0 and {mx if mx is not None else 'the part maximum'}")
        db.execute("UPDATE student_corrections SET status = 'overridden', teacher_total = :t WHERE id = :id", {"t": total, "id": correction_id})
    elif action == "reject":
        db.execute("UPDATE student_corrections SET status = 'rejected', teacher_reason = :r WHERE id = :id",
                   {"r": reason.strip() or "Not accepted", "id": correction_id})
    else:
        raise ApiError(400, "bad_action", "Action must be accept, override or reject")
    return _row(db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": correction_id})[0])


def release_corrections(db: Database, class_assignment_id: int) -> int:
    return db.execute("UPDATE student_corrections SET status = 'released', released_at = CURRENT_TIMESTAMP "
                      "WHERE status IN ('accepted', 'overridden') AND submission_id IN "
                      "(SELECT id FROM submissions WHERE class_assignment_id = :ca)", {"ca": class_assignment_id})


def released_marks(db: Database, submission_id: int) -> Dict[str, dict]:
    """{q_id: {total, max}} of the released corrections of one script — for records and the CSV."""
    rows = db.query("SELECT q_id, remark_total, remark_max, teacher_total FROM student_corrections "
                    "WHERE submission_id = :s AND status = 'released'", {"s": submission_id})
    return {r["q_id"]: {"total": float(r["teacher_total"] if r["teacher_total"] is not None else r["remark_total"] or 0),
                        "max": float(r["remark_max"] or 0)} for r in rows}


def student_reflection(db: Database, ca: Dict[str, Any], detail: dict) -> Dict[str, Any]:
    end = window_end(db, ca)
    open_ = end is not None and _utcnow() < end
    existing = {r["q_id"]: r for r in db.query("SELECT * FROM student_corrections WHERE submission_id = :s", {"s": detail["id"]})}
    parts: Dict[str, dict] = {}
    for key, p in correctable_parts(detail).items():
        c = existing.get(key)
        if c is None:
            parts[key] = {"can_correct": open_, "status": None, "new_mark": None}
        else:
            new = None
            if c["status"] == "released":
                new = float(c["teacher_total"] if c["teacher_total"] is not None else c["remark_total"] or 0)
            parts[key] = {"can_correct": False, "status": c["status"], "new_mark": new}
    days_left = max(0, (end - _utcnow()).days) if end else 0
    return {"window_ends_at": iso_utc(end) if end else None, "days_left": days_left, "parts": parts}
