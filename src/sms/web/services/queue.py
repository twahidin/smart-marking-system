import json
from typing import Any, Dict, List, Optional

from sms.memory.db import Database
from sms.schemas.marking import Rubric
from sms.schemas.scheme import q_label
from sms.storage import PageStorage
from sms.web.errors import ApiError
from sms.web.services.pages_cleanup import effective_delete_pages, mark_pages_deleted, reconcile_done, unlink_pages
from sms.web.services.submissions import iso_utc, mark_key, mark_total, row_key, run_final_v2, run_scheme


def list_queue(db: Database) -> List[Dict[str, Any]]:
    rows = db.query(
        "SELECT q.id, q.submission_id, q.q_id, q.reason, q.created_at, q.run_id, s.label AS submission_label, "
        "mr.rubric_json, mr.extracted_json, mr.marks_json, mr.reviewed_json, mr.final_marks_json "
        "FROM teacher_queue q JOIN marking_runs mr ON mr.run_id = q.run_id "
        "LEFT JOIN submissions s ON s.id = q.submission_id "
        "WHERE q.status = 'pending' ORDER BY q.id"
    )
    sub_ids = sorted({r["submission_id"] for r in rows if r["submission_id"] is not None})
    pages_by_sub: Dict[int, List[int]] = {sid: [] for sid in sub_ids}
    if sub_ids:
        placeholders = ", ".join(f":s{i}" for i in range(len(sub_ids)))
        params = {f"s{i}": sid for i, sid in enumerate(sub_ids)}
        for p in db.query(
            f"SELECT id, submission_id FROM pages WHERE submission_id IN ({placeholders}) "
            "AND kind = 'student' AND deleted_at IS NULL ORDER BY submission_id, page_index",
            params,
        ):
            pages_by_sub[p["submission_id"]].append(p["id"])

    out = []
    for r in rows:
        q = r["q_id"]
        extracted = json.loads(r["extracted_json"] or '{"questions": []}')
        marks = json.loads(r["marks_json"] or '{"marks": []}')
        reviewed = json.loads(r["reviewed_json"] or '{"verdicts": []}')
        eq = next((x for x in extracted.get("questions", []) if x["q_id"] == q), {})
        mq = next((x for x in marks.get("marks", []) if x["q_id"] == q), {})
        rv = next((x for x in reviewed.get("verdicts", []) if x["q_id"] == q), {})
        page_ids = pages_by_sub.get(r["submission_id"], []) if r["submission_id"] else []
        item = {
            "id": r["id"], "submission_id": r["submission_id"], "submission_label": r["submission_label"] or r["run_id"],
            "q_id": q, "reason": r["reason"], "created_at": iso_utc(r["created_at"]),
            "transcription": eq.get("transcribed_answer", ""), "workings": eq.get("workings", ""),
            "reviewer_note": rv.get("reviewer_note", ""),
            "page_ids": page_ids,
        }
        scheme_info = run_scheme(r)
        if scheme_info:
            item.update(_v2_fields(r, scheme_info, q, extracted))
        else:
            item.update({
                "marks_version": 1,
                "proposed_criterion_scores": mq.get("criterion_scores", []), "proposed_total": mq.get("total"),
                "evidence": mq.get("evidence", ""), "rationale": mq.get("rationale", ""),
                "criterion_defs": Rubric.model_validate_json(r["rubric_json"]).model_dump()["criterion_defs"],
            })
        out.append(item)
    return out


def _v2_row_and_mark(run: dict, scheme_info: dict, key: str):
    """(scheme row, stored final mark) for a queue item's part / criterion; either may be None."""
    kind = scheme_info["scheme_kind"]
    row = next((x for x in scheme_info["scheme"] if row_key(kind, x) == key), None)
    final = run_final_v2(run) or {}
    marks = final.get("parts" if kind == "mark_scheme" else "rubric") or []
    mark = next((m for m in marks if mark_key(kind, m) == key), None)
    return row, mark


def _v2_fields(run: dict, scheme_info: dict, key: str, extracted: dict) -> Dict[str, Any]:
    """Queue item fields for a v2 part: the scheme row it is marked against and the stored (merged) mark
    as the proposal — the same mark the detail and the record show, so the three always agree. A rubric
    marks the response as one, so the transcription is the whole script."""
    kind = scheme_info["scheme_kind"]
    row, mark = _v2_row_and_mark(run, scheme_info, key)
    fields: Dict[str, Any] = {
        "marks_version": 2, "scheme_kind": kind,
        "label": q_label(key) if kind == "mark_scheme" else key,
        "scheme_row": row, "proposed": mark,
        "proposed_total": mark_total(kind, mark) if mark else None,
        "proposed_criterion_scores": [], "criterion_defs": [], "evidence": "",
        "rationale": (mark or {}).get("justification", ""),
    }
    if kind == "mark_scheme":
        q = next((x for x in scheme_info["questions"] if x.get("q_id") == key), {})
        fields["question_text"] = q.get("text", "")
    else:
        ex_qs = extracted.get("questions") or []
        fields["question_text"] = "; ".join(q.get("text", "") for q in scheme_info["questions"] if q.get("text"))
        fields["transcription"] = "\n\n".join(t for t in ((x.get("transcribed_answer") or "").strip() for x in ex_qs) if t)
        fields["workings"] = "\n\n".join(t for t in ((x.get("workings") or "").strip() for x in ex_qs) if t)
    return fields


def _v2_correction(run: dict, scheme_info: dict, key: str, allocations: Optional[List[dict]], band: Optional[str]):
    """Validate a v2 resolve body against the scheme and return (criterion_scores_json dict, teacher total,
    agent total). mark_scheme: `allocations` [{label, got}] with labels from the scheme row (or, for a part
    the scheme has no row for, from the marker's own allocations); labels left out count as lost. rubric:
    `band` must be one of the criterion's bands; its marks come from the rubric."""
    kind = scheme_info["scheme_kind"]
    row, mark = _v2_row_and_mark(run, scheme_info, key)
    agent = mark_total(kind, mark) if mark else None
    if kind == "mark_scheme":
        if allocations is None:
            raise ApiError(400, "bad_allocations", "This part is marked against a mark scheme — send the allocations "
                                                   "as [{label, got}]")
        points = row.get("marks") if row else [{"label": a["label"], "marks": a.get("marks", 0)} for a in (mark or {}).get("awarded") or []]
        valid = {p["label"]: int(p.get("marks", 0)) for p in points or []}
        seen = set()
        allocations = [{**a, "label": str(a["label"]).strip()} for a in allocations]
        for a in allocations:
            label = a["label"]
            if label not in valid:
                raise ApiError(400, "bad_allocations", f"{label} is not an allocation of this part ({', '.join(valid) or 'none'})")
            if label in seen:
                raise ApiError(400, "bad_allocations", f"{label} is given twice")
            seen.add(label)
        got = {a["label"]: bool(a["got"]) for a in allocations}
        chosen = [{"label": label, "got": got.get(label, False), "marks": marks} for label, marks in valid.items()]
        total = sum(c["marks"] for c in chosen if c["got"])
        return {"version": 2, "allocations": chosen, "total": total}, total, agent
    if band is None:
        raise ApiError(400, "bad_band", "This criterion is marked against a rubric — send the band")
    bands = {b["band"]: int(b.get("marks", 0)) for b in (row or {}).get("bands") or []}
    if band not in bands:
        raise ApiError(400, "bad_band", f"{band} is not a band of {key} ({', '.join(bands) or 'none'})")
    return {"version": 2, "band": band, "marks": bands[band]}, bands[band], agent


def resolve_queue_item(db: Database, item_id: int, criterion_scores: Optional[List[int]] = None, reason: str = "",
                       *, storage: PageStorage, allocations: Optional[List[dict]] = None,
                       band: Optional[str] = None) -> Dict[str, Any]:
    """Record the teacher's decision on a pending item. v1 items take `criterion_scores` (one per
    criterion); v2 items take `allocations` [{label, got}] (mark scheme) or `band` (rubric), validated
    against the scheme, and store the v2 shape in teacher_corrections.criterion_scores_json. Resolving
    the last pending part flips the script to `done` and deletes its student pages (when the effective
    delete flag is on): rows are marked in the same transaction, files removed after it commits.
    Resolves of one submission serialise on its row (Postgres `FOR UPDATE`); after commit a reconcile
    pass makes sure a script with nothing left pending is `done`, and the returned status is re-read."""
    rows = db.query("SELECT q.run_id, q.q_id, q.submission_id, mr.rubric_json, mr.marks_json, mr.final_marks_json "
                    "FROM teacher_queue q JOIN marking_runs mr ON mr.run_id = q.run_id WHERE q.id = :id AND q.status = 'pending'",
                    {"id": item_id})
    if not rows:
        raise ApiError(404, "not_found", "That question is not waiting for you")
    r = rows[0]
    scheme_info = run_scheme(r)
    if scheme_info:
        if criterion_scores is not None:
            kind = scheme_info["scheme_kind"]
            raise ApiError(400, "bad_allocations" if kind == "mark_scheme" else "bad_band",
                           "This part is marked per part — send allocations (mark scheme) or a band (rubric), not criterion scores")
        scores_json, teacher_mark, agent_mark = _v2_correction(r, scheme_info, r["q_id"], allocations, band)
    else:
        if criterion_scores is None or allocations is not None or band is not None:
            raise ApiError(400, "bad_scores", "This question is marked by criteria — send criterion_scores")
        rubric = Rubric.model_validate_json(r["rubric_json"])
        if len(criterion_scores) != len(rubric.criterion_defs):
            raise ApiError(400, "bad_scores", f"Give one mark per criterion ({len(rubric.criterion_defs)})")
        for score, c in zip(criterion_scores, rubric.criterion_defs):
            if score < 0 or score > c.max_score:
                raise ApiError(400, "bad_scores", f"{c.description}: mark must be between 0 and {c.max_score}")
        marks = json.loads(r["marks_json"] or '{"marks": []}')
        agent_mark = next((m["total"] for m in marks.get("marks", []) if m["q_id"] == r["q_id"]), None)
        scores_json, teacher_mark = criterion_scores, sum(criterion_scores)
    with db.transaction() as tx:
        if r["submission_id"] is not None and not db.is_sqlite:
            tx.query("SELECT id FROM submissions WHERE id = :s FOR UPDATE", {"s": r["submission_id"]})
        changed = tx.execute(
            "UPDATE teacher_queue SET status = 'resolved' WHERE id = :id AND status = 'pending'",
            {"id": item_id},
        )
        if changed != 1:
            raise ApiError(404, "not_found", "That question is not waiting for you")
        tx.execute(
            "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason, criterion_scores_json) "
            "VALUES (:run_id, :q_id, :agent, :teacher, :reason, :scores)",
            {"run_id": r["run_id"], "q_id": r["q_id"], "agent": agent_mark, "teacher": teacher_mark,
             "reason": reason, "scores": json.dumps(scores_json)},
        )
        status = None
        to_unlink: List[str] = []
        if r["submission_id"] is not None:
            remaining = tx.query("SELECT COUNT(*) AS c FROM teacher_queue WHERE submission_id = :s AND status = 'pending'",
                                 {"s": r["submission_id"]})[0]["c"]
            status = "needs_you" if remaining else "done"
            tx.execute("UPDATE submissions SET status = :st, updated_at = CURRENT_TIMESTAMP WHERE id = :s",
                       {"st": status, "s": r["submission_id"]})
            if status == "done" and effective_delete_pages(tx, r["submission_id"]):
                to_unlink = mark_pages_deleted(tx, r["submission_id"])
    unlink_pages(storage, to_unlink)
    if r["submission_id"] is not None:
        if status == "needs_you":
            reconcile_done(db, storage, r["submission_id"])
        status = db.query("SELECT status FROM submissions WHERE id = :s", {"s": r["submission_id"]})[0]["status"]
    return {"id": item_id, "submission_id": r["submission_id"], "submission_status": status}
