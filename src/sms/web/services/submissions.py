import json
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sms.memory.db import Database
from sms.pipeline.router import SubjectRouter
from sms.schemas.marking import Rubric
from sms.schemas.scheme import q_label
from sms.storage import PageStorage, UploadError, process_uploads
from sms.timeutil import iso_utc  # noqa: F401 - re-exported for existing importers
from sms.web.errors import ApiError
from sms.web.services.assignments import get_template, mark_template_used
from sms.web.services.rubric import parse_rubric
from sms.worker.jobs import JobStore


def create_submission(db: Database, storage: PageStorage, jobs: JobStore, *, label: str, subject: str,
                      context: str, rubric_json: str, files: List[Tuple[str, bytes]],
                      assignment_id: Optional[int] = None) -> Dict[str, Any]:
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
    # A stale id from the SPA (template deleted meanwhile) is dropped rather than rejected.
    if assignment_id is not None and get_template(db, assignment_id) is None:
        assignment_id = None
    with db.transaction() as tx:
        sid = tx.insert(
            "INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id) "
            "VALUES (:label, :subject, :context, :rubric, 'uploaded', :aid) RETURNING id",
            {"label": label, "subject": subject, "context": context.strip(), "rubric": rubric.model_dump_json(),
             "aid": assignment_id},
        )
        page_rows = []
        for i, p in enumerate(pages):
            pid = tx.insert(
                "INSERT INTO pages (submission_id, page_index, sha256, storage_path, source_filename, width, height) "
                "VALUES (:s, :i, :h, :p, :f, :w, :ht) RETURNING id",
                {"s": sid, "i": i, "h": p.sha256, "p": p.storage_path, "f": p.source_filename, "w": p.width, "ht": p.height},
            )
            page_rows.append({"id": pid, "page_index": i, "width": p.width, "height": p.height})
    if assignment_id is not None:
        mark_template_used(db, assignment_id)
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


# --- version 2 (per-part) helpers -------------------------------------------------------------
# A v2 run stores final_marks_json {"version": 2, "kind", "parts", "rubric"} and rubric_json
# {"scheme_kind", "questions", "scheme", "notes"}; a v1 run has neither key.

V2_KINDS = ("mark_scheme", "rubric")


def run_scheme(run: Optional[dict]) -> Optional[dict]:
    """The v2 scheme dict of a run ({scheme_kind, questions, scheme, notes}), or None for a v1 run."""
    if not run or not run.get("rubric_json"):
        return None
    try:
        data = json.loads(run["rubric_json"])
    except ValueError:
        return None
    if isinstance(data, dict) and data.get("scheme_kind") in V2_KINDS:
        return {"scheme_kind": data["scheme_kind"], "questions": data.get("questions") or [],
                "scheme": data.get("scheme") or [], "notes": data.get("notes") or ""}
    return None


def run_final_v2(run: dict) -> Optional[dict]:
    """final_marks_json of a v2 run as a dict, or None when the run is v1 / unfinished."""
    if not run.get("final_marks_json"):
        return None
    data = json.loads(run["final_marks_json"])
    return data if isinstance(data, dict) and data.get("version") == 2 else None


def row_key(kind: str, row: dict) -> str:
    return row["q_id"] if kind == "mark_scheme" else row["criterion"]


def row_max(kind: str, row: dict) -> int:
    if kind == "mark_scheme":
        return sum(int(m.get("marks", 0)) for m in row.get("marks") or [])
    return max((int(b.get("marks", 0)) for b in row.get("bands") or []), default=0)


def mark_key(kind: str, mark: dict) -> str:
    return mark["q_id"] if kind == "mark_scheme" else mark["criterion"]


def mark_total(kind: str, mark: dict) -> int:
    return int(mark.get("total" if kind == "mark_scheme" else "marks") or 0)


def correction_total(correction: dict) -> int:
    """The teacher's total in a v2 correction ({total} for a part, {marks} for a band)."""
    return int(correction.get("total", correction.get("marks", 0)) or 0)


def compute_totals_v2(kind: str, scheme: Iterable[dict], marks: Iterable[dict], pending: Set[str],
                      corrections: Dict[str, dict]) -> Dict[str, int]:
    """Totals over the scheme rows in scheme order: a teacher-resolved part counts the teacher's total;
    a pending part counts the marker's total in `total` and the row's max in `total_upper`; any other
    part counts its stored total (0 when the marker returned nothing). `total_max` is the sum of the
    row maxima. Parts outside the scheme (escalated as not in scheme) do not count."""
    by_key = {}
    for m in marks:
        by_key.setdefault(mark_key(kind, m), m)
    total = upper = maximum = 0
    seen: Set[str] = set()
    for row in scheme:
        key = row_key(kind, row)
        if key in seen:
            continue
        seen.add(key)
        rmax = row_max(kind, row)
        maximum += rmax
        if key in corrections:
            t = correction_total(corrections[key]); total += t; upper += t
        elif key in pending:
            t = mark_total(kind, by_key[key]) if key in by_key else 0
            total += t; upper += rmax
        elif key in by_key:
            t = mark_total(kind, by_key[key]); total += t; upper += t
    return {"total": total, "total_upper": upper, "total_max": maximum}


def _run_row(db: Database, run_id: Optional[str]) -> Optional[dict]:
    if not run_id:
        return None
    rows = db.query("SELECT * FROM marking_runs WHERE run_id = :r ORDER BY id DESC LIMIT 1", {"r": run_id})
    return rows[0] if rows else None


def _pending(db: Database, submission_id: int) -> Dict[str, dict]:
    rows = db.query("SELECT id, q_id, reason FROM teacher_queue WHERE submission_id = :s AND status = 'pending'",
                    {"s": submission_id})
    return {r["q_id"]: r for r in rows}


def _correction_rows(db: Database, run_id: Optional[str]) -> List[dict]:
    if not run_id:
        return []
    return db.query("SELECT q_id, criterion_scores_json, teacher_mark FROM teacher_corrections WHERE run_id = :r ORDER BY id",
                    {"r": run_id})


def _corrections(db: Database, run_id: Optional[str]) -> Dict[str, List[int]]:
    """v1 corrections: q_id -> criterion scores (a later correction replaces an earlier one)."""
    out: Dict[str, List[int]] = {}
    for r in _correction_rows(db, run_id):
        if r["criterion_scores_json"]:
            scores = json.loads(r["criterion_scores_json"])
            if isinstance(scores, list):
                out[r["q_id"]] = scores
        elif r["teacher_mark"] is not None:
            out[r["q_id"]] = [int(r["teacher_mark"])]
    return out


def _corrections_v2(db: Database, run_id: Optional[str]) -> Dict[str, dict]:
    """v2 corrections: q_id / criterion -> {"version": 2, "allocations", "total"} or {"version": 2, "band", "marks"}."""
    out: Dict[str, dict] = {}
    for r in _correction_rows(db, run_id):
        if not r["criterion_scores_json"]:
            continue
        data = json.loads(r["criterion_scores_json"])
        if isinstance(data, dict) and data.get("version") == 2:
            out[r["q_id"]] = data
    return out


def _teacher_view(correction: dict) -> dict:
    """The detail's `teacher` field: the stored correction without its version, plus `total`."""
    view = {k: v for k, v in correction.items() if k != "version"}
    view["total"] = correction_total(correction)
    return view


def serialise_parts_v2(scheme_info: dict, final: dict, extracted: dict, pending: Dict[str, dict],
                       corrections: Dict[str, dict]) -> List[dict]:
    """Detail rows for a v2 run: one per scheme row in scheme order (then any part the marker returned
    that the scheme has no row for, escalated as not in scheme). A rubric marks the response as one,
    so every criterion shows the whole transcription."""
    kind = scheme_info["scheme_kind"]
    questions = {q["q_id"]: q for q in scheme_info["questions"]}
    marks = final.get("parts" if kind == "mark_scheme" else "rubric") or []
    by_key: Dict[str, dict] = {}
    for m in marks:
        by_key.setdefault(mark_key(kind, m), m)
    ex_qs = extracted.get("questions") or []
    ex_by_q = {q["q_id"]: q for q in ex_qs}
    whole = "\n\n".join(t for t in ((q.get("transcribed_answer") or "").strip() for q in ex_qs) if t)
    whole_workings = "\n\n".join(t for t in ((q.get("workings") or "").strip() for q in ex_qs) if t)
    any_illegible = any(q.get("needs_human_transcription") for q in ex_qs)

    def build(key: str, row: Optional[dict], mark: Optional[dict]) -> dict:
        if kind == "mark_scheme":
            eq = ex_by_q.get(key, {})
            base = {
                "q_id": key, "label": q_label(key), "question_text": questions.get(key, {}).get("text", ""),
                "scheme": {"answer": row.get("answer", ""), "marks": row.get("marks") or [], "notes": row.get("notes", "")} if row else None,
                "extracted": eq.get("transcribed_answer", ""), "workings": eq.get("workings", ""),
                "illegible": bool(eq.get("needs_human_transcription", False)),
                "awarded": (mark or {}).get("awarded") or [], "total": mark_total(kind, mark) if mark else 0,
                "justification": (mark or {}).get("justification", ""),
                "in_scheme": bool((mark or {}).get("in_scheme", True)),
            }
        else:
            base = {
                "q_id": key, "label": key, "question_text": "; ".join(q.get("text", "") for q in scheme_info["questions"] if q.get("text")),
                "scheme": {"criterion": key, "bands": row.get("bands") or []} if row else None,
                "extracted": whole, "workings": whole_workings, "illegible": any_illegible,
                "band": (mark or {}).get("band", ""), "descriptor_met": (mark or {}).get("descriptor_met", ""),
                "total": mark_total(kind, mark) if mark else 0,
                "justification": (mark or {}).get("justification", ""), "in_scheme": row is not None,
            }
        base["max"] = row_max(kind, row) if row else 0
        base["confidence"] = (mark or {}).get("confidence")
        base["escalated"] = key in pending
        base["reason"] = pending[key]["reason"] if key in pending else None
        base["queue_id"] = pending[key]["id"] if key in pending else None
        base["teacher"] = _teacher_view(corrections[key]) if key in corrections else None
        return base

    out: List[dict] = []
    seen: Set[str] = set()
    for row in scheme_info["scheme"]:
        key = row_key(kind, row)
        if key in seen:
            continue
        seen.add(key)
        out.append(build(key, row, by_key.get(key)))
    for key, m in by_key.items():
        if key not in seen:
            out.append(build(key, None, m))
    return out


def list_submissions(db: Database) -> List[Dict[str, Any]]:
    subs = db.query("SELECT s.*, (SELECT COUNT(*) FROM pages p WHERE p.submission_id = s.id) AS page_count, "
                    "a.title AS assignment_title "
                    "FROM submissions s LEFT JOIN assignment_templates a ON a.id = s.assignment_id ORDER BY s.id DESC")
    out = []
    for s in subs:
        rubric = Rubric.model_validate_json(s["rubric_json"])
        run = _run_row(db, s["run_id"])
        pending = _pending(db, s["id"])
        scheme_info = run_scheme(run)
        totals = None
        if scheme_info and run:
            final_v2 = run_final_v2(run)
            if final_v2:
                kind = scheme_info["scheme_kind"]
                totals = compute_totals_v2(kind, scheme_info["scheme"], final_v2.get("parts" if kind == "mark_scheme" else "rubric") or [],
                                           set(pending), _corrections_v2(db, s["run_id"]))
        elif run and run["final_marks_json"]:
            final = json.loads(run["final_marks_json"]).get("marks") or []
            totals = compute_totals(rubric, final, set(pending), _corrections(db, s["run_id"])) if final else None
        out.append({
            "id": s["id"], "label": s["label"], "subject": s["subject"], "page_count": s["page_count"],
            "status": s["status"], "created_at": iso_utc(s["created_at"]),
            "assignment_id": s["assignment_id"], "assignment_title": s["assignment_title"],
            "total": totals["total"] if totals else None,
            "total_upper": totals["total_upper"] if totals else None,
            "total_max": totals["total_max"] if totals else None,
            "needs_you_qids": sorted(pending),
        })
    return out


def get_submission(db: Database, jobs: JobStore, submission_id: int) -> Optional[Dict[str, Any]]:
    rows = db.query("SELECT s.*, a.title AS assignment_title FROM submissions s "
                    "LEFT JOIN assignment_templates a ON a.id = s.assignment_id WHERE s.id = :id", {"id": submission_id})
    if not rows:
        return None
    s = rows[0]
    rubric = Rubric.model_validate_json(s["rubric_json"])
    pages = [{"id": p["id"], "page_index": p["page_index"], "width": p["width"], "height": p["height"],
              "deleted": p["deleted_at"] is not None}
             for p in db.query("SELECT id, page_index, width, height, deleted_at FROM pages WHERE submission_id = :id "
                               "AND kind = 'student' ORDER BY page_index", {"id": submission_id})]
    run = _run_row(db, s["run_id"])
    pending = _pending(db, submission_id)
    corrections = _corrections(db, s["run_id"])
    per_q_max = sum(c.max_score for c in rubric.criterion_defs)
    marks: List[dict] = []
    parts: List[dict] = []
    totals = None
    marks_version = 1
    feedback = None
    scheme_info = run_scheme(run)
    if run and scheme_info:
        marks_version = 2
        final_v2 = run_final_v2(run) or {"kind": scheme_info["scheme_kind"], "parts": [], "rubric": []}
        extracted = json.loads(run["extracted_json"]) if run["extracted_json"] else {"questions": []}
        corrections_v2 = _corrections_v2(db, s["run_id"])
        parts = serialise_parts_v2(scheme_info, final_v2, extracted, pending, corrections_v2)
        kind = scheme_info["scheme_kind"]
        totals = compute_totals_v2(kind, scheme_info["scheme"], final_v2.get("parts" if kind == "mark_scheme" else "rubric") or [],
                                   set(pending), corrections_v2)
        feedback = json.loads(run["feedback_json"]) if run["feedback_json"] else None
    elif run:
        final = json.loads(run["final_marks_json"]).get("marks") or [] if run["final_marks_json"] else []
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
        totals = compute_totals(rubric, marks, set(pending), corrections) if marks else None
    job = jobs.job_for_submission(submission_id)
    return {
        "id": s["id"], "label": s["label"], "subject": s["subject"], "context": s["context"], "status": s["status"],
        "created_at": iso_utc(s["created_at"]), "rubric": rubric.model_dump(), "pages": pages,
        "pages_deleted": bool(pages) and all(p["deleted"] for p in pages), "marks": marks,
        "marks_version": marks_version, "parts": parts, "run_id": s["run_id"],
        "marked_at": iso_utc(run["created_at"]) if run else None,
        "scheme_kind": scheme_info["scheme_kind"] if scheme_info else None,
        "assignment_id": s["assignment_id"], "assignment_title": s["assignment_title"],
        "totals": totals,
        "feedback": feedback,
        "job": {"status": job["status"], "attempts": job["attempts"], "error": job["error"],
                "started_at": iso_utc(job["started_at"]),
                "finished_at": iso_utc(job["finished_at"])} if job else None,
    }
