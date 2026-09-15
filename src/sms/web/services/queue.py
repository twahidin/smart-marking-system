import json
from typing import Any, Dict, List

from sms.memory.db import Database
from sms.schemas.marking import Rubric
from sms.web.errors import ApiError
from sms.web.services.submissions import iso_utc


def list_queue(db: Database) -> List[Dict[str, Any]]:
    rows = db.query(
        "SELECT q.id, q.submission_id, q.q_id, q.reason, q.created_at, q.run_id, s.label AS submission_label, "
        "mr.rubric_json, mr.extracted_json, mr.marks_json, mr.reviewed_json "
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
            "ORDER BY submission_id, page_index",
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
        out.append({
            "id": r["id"], "submission_id": r["submission_id"], "submission_label": r["submission_label"] or r["run_id"],
            "q_id": q, "reason": r["reason"], "created_at": iso_utc(r["created_at"]),
            "transcription": eq.get("transcribed_answer", ""), "workings": eq.get("workings", ""),
            "proposed_criterion_scores": mq.get("criterion_scores", []), "proposed_total": mq.get("total"),
            "evidence": mq.get("evidence", ""), "rationale": mq.get("rationale", ""),
            "reviewer_note": rv.get("reviewer_note", ""),
            "criterion_defs": Rubric.model_validate_json(r["rubric_json"]).model_dump()["criterion_defs"],
            "page_ids": page_ids,
        })
    return out


def resolve_queue_item(db: Database, item_id: int, criterion_scores: List[int], reason: str) -> Dict[str, Any]:
    rows = db.query("SELECT q.run_id, q.q_id, q.submission_id, mr.rubric_json, mr.marks_json FROM teacher_queue q "
                    "JOIN marking_runs mr ON mr.run_id = q.run_id WHERE q.id = :id AND q.status = 'pending'",
                    {"id": item_id})
    if not rows:
        raise ApiError(404, "not_found", "That question is not waiting for you")
    r = rows[0]
    rubric = Rubric.model_validate_json(r["rubric_json"])
    if len(criterion_scores) != len(rubric.criterion_defs):
        raise ApiError(400, "bad_scores", f"Give one mark per criterion ({len(rubric.criterion_defs)})")
    for score, c in zip(criterion_scores, rubric.criterion_defs):
        if score < 0 or score > c.max_score:
            raise ApiError(400, "bad_scores", f"{c.description}: mark must be between 0 and {c.max_score}")
    marks = json.loads(r["marks_json"] or '{"marks": []}')
    agent_mark = next((m["total"] for m in marks.get("marks", []) if m["q_id"] == r["q_id"]), None)
    with db.transaction() as tx:
        changed = tx.execute(
            "UPDATE teacher_queue SET status = 'resolved' WHERE id = :id AND status = 'pending'",
            {"id": item_id},
        )
        if changed != 1:
            raise ApiError(404, "not_found", "That question is not waiting for you")
        tx.execute(
            "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason, criterion_scores_json) "
            "VALUES (:run_id, :q_id, :agent, :teacher, :reason, :scores)",
            {"run_id": r["run_id"], "q_id": r["q_id"], "agent": agent_mark, "teacher": sum(criterion_scores),
             "reason": reason, "scores": json.dumps(criterion_scores)},
        )
        status = None
        if r["submission_id"] is not None:
            remaining = tx.query("SELECT COUNT(*) AS c FROM teacher_queue WHERE submission_id = :s AND status = 'pending'",
                                 {"s": r["submission_id"]})[0]["c"]
            status = "needs_you" if remaining else "done"
            tx.execute("UPDATE submissions SET status = :st, updated_at = CURRENT_TIMESTAMP WHERE id = :s",
                       {"st": status, "s": r["submission_id"]})
    return {"id": item_id, "submission_id": r["submission_id"], "submission_status": status}
