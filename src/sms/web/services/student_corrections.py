"""Reflect and correct: after feedback is released, a student has a window (reflect_days) to send one
correction per part that lost marks. The AI re-marks it (sms.worker.remark_job); the teacher accepts,
overrides or rejects; releasing makes the new mark visible. Never confuse with teacher_corrections,
which are the teacher's own Review decisions."""
import io
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from sqlalchemy.exc import IntegrityError

from sms.memory.db import Database
from sms.schemas.scheme import norm_qid
from sms.storage import PageStorage
from sms.timeutil import iso_utc
from sms.web.errors import ApiError
from sms.web.services.class_assignments import effective_reflect_days
from sms.web.services.pages_cleanup import effective_retention, unlink_pages
from sms.worker.jobs import JobStore, _payload_json

REASONS = ("sign", "method", "rushed", "misread", "other")
# What a student may see of a correction's state: the teacher's decision stays hidden until it is released.
STUDENT_STATUS = {"submitted": "sent", "remarked": "waiting", "accepted": "waiting", "overridden": "waiting",
                  "released": "released", "rejected": "rejected"}
FINAL = ("released", "rejected")
MAX_TEXT = 4000


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
    if len(text) > MAX_TEXT:
        raise ApiError(400, "too_long", "Keep your correction under 4,000 characters")
    sid = submission_detail["id"]
    if db.query("SELECT 1 FROM student_corrections WHERE submission_id = :s AND q_id = :q", {"s": sid, "q": key}):
        raise ApiError(409, "already_corrected", "You have already sent a correction for this part")
    data = _jpeg(photo) if photo is not None else None
    digest, rel = storage.put_jpeg(data) if data is not None else (None, None)
    try:
        # Page, correction and remark job commit together: a duplicate or a failed enqueue leaves nothing behind.
        with db.transaction() as tx:
            page_id = None
            if digest is not None:
                n = tx.query("SELECT COUNT(*) AS c FROM pages WHERE submission_id = :s", {"s": sid})[0]["c"]
                page_id = tx.insert("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height, kind) "
                                    "VALUES (:s, :i, :d, :p, 0, 0, 'correction') RETURNING id",
                                    {"s": sid, "i": 1000 + int(n), "d": digest, "p": rel})
            # The part's max bounds an override even when the re-mark fails (the job may refine it); the
            # original mark is the "first try" the teacher sees beside the correction.
            cid = tx.insert("INSERT INTO student_corrections (submission_id, q_id, reason, text, page_id, status, remark_max, original_total) "
                            "VALUES (:s, :q, :r, :t, :p, 'submitted', :mx, :orig) RETURNING id",
                            {"s": sid, "q": key, "r": reason if reason in REASONS else "other", "t": text or None, "p": page_id,
                             "mx": parts[key]["max"], "orig": parts[key]["mark"]})
            # Same row JobStore.enqueue writes, but without a submission_id (the script keeps its status).
            tx.insert("INSERT INTO jobs (kind, submission_id, status, payload_json) VALUES ('remark', NULL, 'queued', :p) RETURNING id",
                      {"p": _payload_json({"correction_id": cid})})
    except IntegrityError as e:
        raise ApiError(409, "already_corrected", "You have already sent a correction for this part") from e
    return _row(db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": cid})[0])


def list_corrections(db: Database, class_assignment_id: int) -> List[Dict[str, Any]]:
    """Each correction with its first try (`original_total` / `original_max`) and the part's answer crop.
    A photo deleted under the retention setting is listed as no photo (`page_id` None)."""
    rows = db.query("SELECT c.*, s.label AS submission_label, st.reg_no AS reg_no, st.name AS student_name, "
                    "p.deleted_at AS photo_deleted_at "
                    "FROM student_corrections c JOIN submissions s ON s.id = c.submission_id "
                    "LEFT JOIN students st ON st.id = s.student_id LEFT JOIN pages p ON p.id = c.page_id "
                    "WHERE s.class_assignment_id = :ca ORDER BY c.id", {"ca": class_assignment_id})
    crops: Dict[Tuple[int, str], int] = {}
    if rows:
        for c in db.query("SELECT pc.id, pc.submission_id, pc.q_id FROM part_crops pc JOIN submissions s ON s.id = pc.submission_id "
                          "WHERE s.class_assignment_id = :ca AND pc.deleted_at IS NULL ORDER BY pc.id", {"ca": class_assignment_id}):
            crops.setdefault((c["submission_id"], norm_qid(c["q_id"])), c["id"])
    out = []
    for r in rows:
        r = dict(r)
        if r.pop("photo_deleted_at") is not None:
            r["page_id"] = None
        r["original_max"] = r["remark_max"]
        r["crop_id"] = crops.get((r["submission_id"], norm_qid(r["q_id"])))
        out.append(_row(r))
    return out


def _retire_photo(tx, r: dict) -> List[str]:
    """A correction just became final: delete its photo unless the assignment keeps pages (retention
    'pages'). Marks the page row deleted inside `tx` and returns the file to unlink after commit, when no
    other undeleted page shares the content-addressed path."""
    if r["page_id"] is None or effective_retention(tx, r["submission_id"]) == "pages":
        return []
    rows = tx.query("SELECT storage_path FROM pages WHERE id = :p AND deleted_at IS NULL", {"p": r["page_id"]})
    if not rows:
        return []
    tx.execute("UPDATE pages SET deleted_at = CURRENT_TIMESTAMP WHERE id = :p", {"p": r["page_id"]})
    path = rows[0]["storage_path"]
    still = tx.query("SELECT COUNT(*) AS c FROM pages WHERE storage_path = :p AND deleted_at IS NULL", {"p": path})[0]["c"]
    return [] if still else [path]


def decide(db: Database, correction_id: int, action: str, *, total: Optional[float] = None, reason: str = "",
           storage: Optional[PageStorage] = None) -> Dict[str, Any]:
    """Accept, override or reject one correction. A reject is final, so its photo goes with the retention
    setting; pass `storage` so the file is unlinked as well (the route always does)."""
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
        mx = r["remark_max"]   # the part's max, set when the correction was sent
        if mx is None:
            raise ApiError(409, "no_max", "This correction has no part maximum to mark against")
        if total is None or not 0 <= total <= float(mx):
            raise ApiError(400, "bad_total", f"Mark must be between 0 and {float(mx):g}")
        db.execute("UPDATE student_corrections SET status = 'overridden', teacher_total = :t WHERE id = :id", {"t": total, "id": correction_id})
    elif action == "reject":
        with db.transaction() as tx:
            changed = tx.execute("UPDATE student_corrections SET status = 'rejected', teacher_reason = :r "
                                 "WHERE id = :id AND status NOT IN ('released', 'rejected')",
                                 {"r": reason.strip() or "Not accepted", "id": correction_id})
            paths = _retire_photo(tx, r) if changed else []
        if storage is not None:
            unlink_pages(storage, paths)
    else:
        raise ApiError(400, "bad_action", "Action must be accept, override or reject")
    return _row(db.query("SELECT * FROM student_corrections WHERE id = :id", {"id": correction_id})[0])


def release_corrections(db: Database, class_assignment_id: int, storage: Optional[PageStorage] = None) -> int:
    """Release every decided correction of a class set; released photos go with the retention setting
    (pass `storage` so the files are unlinked as well — the route always does)."""
    paths: List[str] = []
    with db.transaction() as tx:
        rows = tx.query("SELECT c.id, c.submission_id, c.page_id FROM student_corrections c JOIN submissions s ON s.id = c.submission_id "
                        "WHERE c.status IN ('accepted', 'overridden') AND s.class_assignment_id = :ca ORDER BY c.id",
                        {"ca": class_assignment_id})
        released = 0
        for r in rows:
            if tx.execute("UPDATE student_corrections SET status = 'released', released_at = CURRENT_TIMESTAMP "
                          "WHERE id = :id AND status IN ('accepted', 'overridden')", {"id": r["id"]}):
                released += 1
                paths += _retire_photo(tx, r)
    if storage is not None:
        unlink_pages(storage, paths)
    return released


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
            status = STUDENT_STATUS.get(c["status"], "waiting")
            if status == "sent" and c["error"]:
                status = "waiting"     # the re-mark failed: it is with the teacher now
            parts[key] = {"can_correct": False, "status": status, "new_mark": new}
    # whole days left, rounded up: the last day still reads "1 day left"
    days_left = max(0, math.ceil((end - _utcnow()).total_seconds() / 86400)) if end else 0
    return {"window_ends_at": iso_utc(end) if end else None, "days_left": days_left, "parts": parts}
