from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from sms.web.deps import get_db, get_jobs, get_settings_store, get_storage, require_teacher
from sms.web.errors import ApiError
from sms.web.services.submissions import create_submission, get_submission, list_submissions
from sms.web.uploads import check_content_length, read_upload_files

router = APIRouter(prefix="/api/submissions", tags=["submissions"], dependencies=[Depends(require_teacher)])


@router.post("", status_code=202)
async def create(request: Request, label: str = Form(...), subject: str = Form("math"), context: str = Form(""),
                 rubric: str = Form(...), assignment_id: Optional[int] = Form(None),
                 files: List[UploadFile] = File(...),
                 db=Depends(get_db), storage=Depends(get_storage), jobs=Depends(get_jobs),
                 settings=Depends(get_settings_store)):
    check_content_length(request)
    has_key = await run_in_threadpool(lambda: settings.load().has_key)
    if not has_key:
        raise ApiError(400, "no_key", "Add an API key under Settings before marking")
    payload = await read_upload_files(request, files)
    # PDF rasterising and image normalising are CPU-bound; keep them off the event loop so
    # other requests (health checks included) are not stalled by a big upload.
    return await run_in_threadpool(create_submission, db, storage, jobs, label=label, subject=subject,
                                   context=context, rubric_json=rubric, files=payload,
                                   assignment_id=assignment_id)


@router.get("")
def index(db=Depends(get_db)):
    return list_submissions(db)


@router.get("/{submission_id}")
def detail(submission_id: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    sub = get_submission(db, jobs, submission_id)
    if sub is None:
        raise ApiError(404, "not_found", "No such submission")
    return sub


@router.post("/{submission_id}/retry", status_code=202)
def retry(submission_id: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    job = jobs.job_for_submission(submission_id)
    if job is None:
        raise ApiError(404, "not_found", "No such submission")
    if job["status"] != "failed":
        raise ApiError(409, "not_failed", "Only failed submissions can be retried")
    jobs.enqueue("mark", submission_id)
    return JSONResponse(status_code=202, content={"id": submission_id, "status": "queued"})
