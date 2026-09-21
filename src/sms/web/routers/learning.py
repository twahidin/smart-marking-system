from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from sms.learning.reflection_job import activate_exemplar, activate_note
from sms.memory.metrics import MetricsSummary
from sms.pipeline.router import SubjectRouter
from sms.web.deps import get_db, get_jobs, require_teacher
from sms.web.errors import ApiError
from sms.web.services.submissions import iso_utc

router = APIRouter(prefix="/api", tags=["learning"], dependencies=[Depends(require_teacher)])


def _subject_list() -> str:
    """"math, language, science, mt or computing" — from the router, so nothing is left behind when
    a subject is added."""
    known = list(SubjectRouter.KNOWN_SUBJECTS)
    return ", ".join(known[:-1]) + " or " + known[-1]


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


class ReflectBody(BaseModel):
    subject: str
    lookback_days: int = Field(default=7, ge=1, le=365)


@router.post("/reflect", status_code=202)
def reflect(body: ReflectBody, jobs=Depends(get_jobs)):
    try:
        subject = SubjectRouter().resolve(body.subject)
    except KeyError:
        # Named from the router's own list, so MT and Computing — reflectable since slice 4 — are not
        # left out of the message the way they were out of the stale hard-coded three.
        raise ApiError(400, "bad_subject", "Subject must be " + _subject_list())
    # The 409 is decided by the insert itself (partial unique index on dedupe_key), so two racing
    # requests — or a request racing the nightly scheduler — cannot both create a job.
    job_id = jobs.enqueue_unique("reflect", {"subject": subject, "lookback_days": body.lookback_days},
                                 dedupe_key=f"reflect:{subject}")
    if job_id is None:
        raise ApiError(409, "already_running", "Reflection is already queued for this subject")
    return JSONResponse(status_code=202, content={"job_id": job_id})


@router.get("/reflect/runs")
def reflect_runs(db=Depends(get_db), jobs=Depends(get_jobs)):
    rows = db.query("SELECT id, subject, lookback_days, proposed_notes, started_at, finished_at, error "
                    "FROM reflection_runs ORDER BY id DESC LIMIT 20")
    runs = []
    for r in rows:
        row = dict(r)
        row["started_at"] = iso_utc(row["started_at"])
        row["finished_at"] = iso_utc(row["finished_at"])
        runs.append(row)
    return {"runs": runs, "pending": sorted(jobs.pending_reflect_subjects())}
