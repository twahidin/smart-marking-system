import json
from typing import Any

from sms.memory.db import Database
from sms.schemas.reflection import CorrectionRow, ReflectionInput


def run_reflection(db: Database, agent: Any, subject: str, lookback_days: int = 7) -> int:
    """Run the nightly reflection job over recent teacher corrections.

    Returns the number of proposed rubric notes (written as draft).
    """
    rows = db.query(
        "SELECT tc.run_id, tc.q_id, tc.agent_mark, tc.teacher_mark, tc.reason, mr.subject, "
        "mr.rubric_json, mr.extracted_json "
        "FROM teacher_corrections tc JOIN marking_runs mr ON tc.run_id = mr.run_id "
        "WHERE mr.subject = ? AND tc.created_at >= datetime('now', ?) AND tc.agent_mark != tc.teacher_mark",
        (subject, f"-{lookback_days} days"),
    )
    if not rows:
        return 0

    corrections = []
    for r in rows:
        extracted = json.loads(r["extracted_json"]) if r["extracted_json"] else {"questions": []}
        answers = {q["q_id"]: q.get("transcribed_answer", "") for q in extracted.get("questions", [])}
        corrections.append(
            CorrectionRow(
                run_id=r["run_id"],
                q_id=r["q_id"],
                subject=r["subject"],
                rubric_json=r["rubric_json"] or "{}",
                extracted_answer=answers.get(r["q_id"], ""),
                agent_mark=r["agent_mark"],
                teacher_mark=r["teacher_mark"],
                reason=r["reason"] or "",
            )
        )

    update = agent.run(ReflectionInput(corrections=corrections))

    for note in update.rubric_notes:
        db.execute(
            "INSERT INTO rubric_notes (subject, note, status, source_run_ids_json) VALUES (?, ?, 'draft', ?)",
            (note.subject, note.note, json.dumps(note.source_run_ids)),
        )
    for case in update.exemplar_cases:
        db.execute(
            "INSERT INTO exemplar_cases (subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')",
            (case.subject, case.topic, case.q_id, case.answer_text, case.awarded, case.max_score, case.why_it_matters),
        )
    return len(update.rubric_notes)


def activate_note(db: Database, note_id: int) -> None:
    db.execute("UPDATE rubric_notes SET status = 'active' WHERE id = ?", (note_id,))


def activate_exemplar(db: Database, exemplar_id: int) -> None:
    db.execute("UPDATE exemplar_cases SET status = 'active' WHERE id = ?", (exemplar_id,))
