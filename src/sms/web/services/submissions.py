import json
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from pydantic import ValidationError

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import Rubric
from sms.storage import PageStorage, UploadError, process_uploads
from sms.timeutil import iso_utc  # noqa: F401 - re-exported for existing importers
from sms.web.errors import ApiError
from sms.worker.jobs import JobStore


def parse_rubric(rubric_json: str) -> Rubric:
    try:
        rubric = Rubric.model_validate_json(rubric_json)
    except ValidationError as e:
        raise ApiError(400, "bad_rubric", f"Rubric is not valid: {e.errors()[0]['msg']}")
    if not rubric.criterion_defs:
        raise ApiError(400, "bad_rubric", "Add at least one criterion")
    return rubric


def create_submission(db: Database, storage: PageStorage, jobs: JobStore, *, label: str, subject: str,
                      context: str, rubric_json: str, files: List[Tuple[str, bytes]]) -> Dict[str, Any]:
    label = label.strip()
    if not label:
        raise ApiError(400, "bad_label", "Give the script a label")
    try:
        subject = SubjectRouter().resolve(subject)
    except KeyError:
        raise ApiError(400, "bad_subject", "Subject must be math, language or science")
    rubric = parse_rubric(rubric_json)
    if not files:
        raise ApiError(400, "no_files", "Add at least one page")
    try:
        pages = process_uploads(files, storage)
    except UploadError as e:
        raise ApiError(400, "bad_upload", str(e))
    with db.transaction() as tx:
        sid = tx.insert(
            "INSERT INTO submissions (label, subject, context, rubric_json, status) "
            "VALUES (:label, :subject, :context, :rubric, 'uploaded') RETURNING id",
            {"label": label, "subject": subject, "context": context.strip(), "rubric": rubric.model_dump_json()},
        )
        page_rows = []
        for i, p in enumerate(pages):
            pid = tx.insert(
                "INSERT INTO pages (submission_id, page_index, sha256, storage_path, source_filename, width, height) "
                "VALUES (:s, :i, :h, :p, :f, :w, :ht) RETURNING id",
                {"s": sid, "i": i, "h": p.sha256, "p": p.storage_path, "f": p.source_filename, "w": p.width, "ht": p.height},
            )
            page_rows.append({"id": pid, "page_index": i, "width": p.width, "height": p.height})
    jobs.enqueue("mark", sid)
    return {"id": sid, "status": "queued", "pages": page_rows}


def compute_totals(rubric: Rubric, final_marks: Iterable[dict], pending_qids: Set[str],
                   corrections: Dict[str, List[int]]) -> Dict[str, int]:
    per_q_max = sum(c.max_score for c in rubric.criterion_defs)
    total = upper = 0
    n = 0
    for m in final_marks:
        n += 1
        q = m["q_id"]
        if q in corrections:
            t = sum(corrections[q]); total += t; upper += t
        elif q in pending_qids:
            total += int(m["total"]); upper += per_q_max
        else:
            total += int(m["total"]); upper += int(m["total"])
    return {"total": total, "total_upper": upper, "total_max": per_q_max * n}


def _run_row(db: Database, run_id: Optional[str]) -> Optional[dict]:
    if not run_id:
        return None
    rows = db.query("SELECT * FROM marking_runs WHERE run_id = :r ORDER BY id DESC LIMIT 1", {"r": run_id})
    return rows[0] if rows else None


def _pending(db: Database, submission_id: int) -> Dict[str, dict]:
    rows = db.query("SELECT id, q_id, reason FROM teacher_queue WHERE submission_id = :s AND status = 'pending'",
                    {"s": submission_id})
    return {r["q_id"]: r for r in rows}


def _corrections(db: Database, run_id: Optional[str]) -> Dict[str, List[int]]:
    if not run_id:
        return {}
    rows = db.query("SELECT q_id, criterion_scores_json, teacher_mark FROM teacher_corrections WHERE run_id = :r ORDER BY id",
                    {"r": run_id})
    out: Dict[str, List[int]] = {}
    for r in rows:
        if r["criterion_scores_json"]:
            out[r["q_id"]] = json.loads(r["criterion_scores_json"])
        elif r["teacher_mark"] is not None:
            out[r["q_id"]] = [int(r["teacher_mark"])]
    return out


def list_submissions(db: Database) -> List[Dict[str, Any]]:
    subs = db.query("SELECT s.*, (SELECT COUNT(*) FROM pages p WHERE p.submission_id = s.id) AS page_count "
                    "FROM submissions s ORDER BY s.id DESC")
    out = []
    for s in subs:
        rubric = Rubric.model_validate_json(s["rubric_json"])
        run = _run_row(db, s["run_id"])
        pending = _pending(db, s["id"])
        final = json.loads(run["final_marks_json"])["marks"] if run and run["final_marks_json"] else []
        totals = compute_totals(rubric, final, set(pending), _corrections(db, s["run_id"])) if final else None
        out.append({
            "id": s["id"], "label": s["label"], "subject": s["subject"], "page_count": s["page_count"],
            "status": s["status"], "created_at": iso_utc(s["created_at"]),
            "total": totals["total"] if totals else None,
            "total_upper": totals["total_upper"] if totals else None,
            "total_max": totals["total_max"] if totals else None,
            "needs_you_qids": sorted(pending),
        })
    return out


def get_submission(db: Database, jobs: JobStore, submission_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query("SELECT * FROM submissions WHERE id = :id", {"id": submission_id})
    if not rows:
        return None
    s = rows[0]
    rubric = Rubric.model_validate_json(s["rubric_json"])
    pages = db.query("SELECT id, page_index, width, height FROM pages WHERE submission_id = :id ORDER BY page_index",
                     {"id": submission_id})
    run = _run_row(db, s["run_id"])
    pending = _pending(db, submission_id)
    corrections = _corrections(db, s["run_id"])
    per_q_max = sum(c.max_score for c in rubric.criterion_defs)
    marks: List[dict] = []
    feedback = None
    if run:
        final = json.loads(run["final_marks_json"])["marks"] if run["final_marks_json"] else []
        for m in final:
            q = m["q_id"]
            marks.append({
                "q_id": q, "criterion_scores": m["criterion_scores"], "total": m["total"], "max": per_q_max,
                "confidence": m.get("confidence"), "evidence": m.get("evidence", ""), "rationale": m.get("rationale", ""),
                "escalated": q in pending, "reason": pending[q]["reason"] if q in pending else None,
                "queue_id": pending[q]["id"] if q in pending else None,
                "teacher_scores": corrections.get(q),
            })
        feedback = json.loads(run["feedback_json"]) if run["feedback_json"] else None
    job = jobs.job_for_submission(submission_id)
    return {
        "id": s["id"], "label": s["label"], "subject": s["subject"], "context": s["context"], "status": s["status"],
        "created_at": iso_utc(s["created_at"]), "rubric": rubric.model_dump(), "pages": pages, "marks": marks,
        "totals": compute_totals(rubric, marks, set(pending), corrections) if marks else None,
        "feedback": feedback,
        "job": {"status": job["status"], "attempts": job["attempts"], "error": job["error"],
                "started_at": iso_utc(job["started_at"]),
                "finished_at": iso_utc(job["finished_at"])} if job else None,
    }
