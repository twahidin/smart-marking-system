from fastapi import APIRouter, Depends

from sms.learning.reflection_job import activate_exemplar, activate_note
from sms.memory.metrics import MetricsSummary
from sms.web.deps import get_db, require_teacher
from sms.web.errors import ApiError
from sms.web.services.submissions import iso_utc

router = APIRouter(prefix="/api", tags=["learning"], dependencies=[Depends(require_teacher)])


def _with_iso_created_at(rows):
    out = []
    for r in rows:
        row = dict(r)
        row["created_at"] = iso_utc(row["created_at"])
        out.append(row)
    return out


@router.get("/notes")
def notes(db=Depends(get_db)):
    rows = db.query("SELECT id, subject, note, status, created_at FROM rubric_notes ORDER BY id DESC")
    return _with_iso_created_at(rows)


@router.post("/notes/{note_id}/approve")
def approve_note(note_id: int, db=Depends(get_db)):
    if not db.query("SELECT id FROM rubric_notes WHERE id = :id", {"id": note_id}):
        raise ApiError(404, "not_found", "No such note")
    activate_note(db, note_id)
    return db.query("SELECT id, subject, note, status FROM rubric_notes WHERE id = :id", {"id": note_id})[0]


@router.get("/exemplars")
def exemplars(db=Depends(get_db)):
    rows = db.query("SELECT id, subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status, created_at "
                    "FROM exemplar_cases ORDER BY id DESC")
    return _with_iso_created_at(rows)


@router.post("/exemplars/{exemplar_id}/approve")
def approve_exemplar(exemplar_id: int, db=Depends(get_db)):
    if not db.query("SELECT id FROM exemplar_cases WHERE id = :id", {"id": exemplar_id}):
        raise ApiError(404, "not_found", "No such exemplar")
    activate_exemplar(db, exemplar_id)
    return db.query("SELECT id, subject, topic, status FROM exemplar_cases WHERE id = :id", {"id": exemplar_id})[0]


@router.get("/stats")
def stats(db=Depends(get_db)):
    ms = MetricsSummary(db)
    return {role: ms.summarize(agent_role=role) for role in ("extractor", "marker", "reviewer", "feedback", "reflection")}
