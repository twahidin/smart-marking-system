"""Marking record downloads: one .docx per script, or a .zip of many plus markbook.xlsx. Generated
on request from the stored marks and streamed, never stored."""
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from sms.records.builder import Record, build_record
from sms.records.bundle import SUFFIX, bundle_zip, record_filename
from sms.records.docx import render_docx
from sms.web.deps import get_db, get_jobs, get_settings_store, require_teacher
from sms.web.errors import ApiError
from sms.web.services.assignments import get_template
from sms.web.services.submissions import get_submission

# Same prefix as the submissions router; registered before it in app.py so /records.zip is never
# read as a submission id.
router = APIRouter(prefix="/api/submissions", tags=["records"], dependencies=[Depends(require_teacher)])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ZipBody(BaseModel):
    ids: List[int]


def _record(db, jobs, model: str, submission_id: int) -> Record:
    detail = get_submission(db, jobs, submission_id)
    if detail is None:
        raise ApiError(404, "not_found", f"No such submission ({submission_id})")
    if not detail.get("run_id"):
        raise ApiError(409, "not_marked", f"{detail['label']} has not been marked yet")
    template = get_template(db, detail["assignment_id"]) if detail.get("assignment_id") is not None else None
    return build_record(detail, template, model=model)


def _model_line(settings_store) -> str:
    # TODO: "Marked by" is the provider/model configured now, not necessarily the one that marked the script.
    # Store provider and model on marking_runs at marking time and read them from the run here.
    s = settings_store.load()
    return f"{s.provider} · {s.model}" if s.model else s.provider


@router.get("/{submission_id}/record.docx")
async def record_docx(submission_id: int, db=Depends(get_db), jobs=Depends(get_jobs), settings=Depends(get_settings_store)):
    def build() -> tuple:
        record = _record(db, jobs, _model_line(settings), submission_id)
        return record, render_docx(record)
    record, data = await run_in_threadpool(build)
    return Response(content=data, media_type=DOCX, headers={"Content-Disposition": _disposition(record)})


def _disposition(record: Record) -> str:
    """ASCII `filename` for every client plus RFC 5987 `filename*` carrying the original label."""
    ascii_name = record_filename(record.student, record.submission_id)
    original = quote((record.student.strip() or ascii_name[:-len(SUFFIX)]).replace('"', "") + SUFFIX, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{original}'


@router.post("/records.zip")
async def records_zip(body: ZipBody, db=Depends(get_db), jobs=Depends(get_jobs), settings=Depends(get_settings_store)):
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise ApiError(400, "no_ids", "Choose at least one script")

    def build() -> bytes:
        model = _model_line(settings)
        return bundle_zip([_record(db, jobs, model, sid) for sid in ids])
    data = await run_in_threadpool(build)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="marking-records.zip"'})
