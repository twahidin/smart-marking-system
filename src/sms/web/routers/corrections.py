"""Reflect and correct over HTTP: a student sends one correction per part; the teacher reviews and releases."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sms.web.deps import get_db, get_jobs, get_storage, require_student, require_teacher
from sms.web.errors import ApiError
from sms.web.services.class_assignments import get_class_assignment
from sms.web.services.student import _status, _visible
from sms.web.services.student_corrections import decide, list_corrections, release_corrections, submit_correction
from sms.web.services.submissions import get_submission
from sms.web.uploads import check_content_length, read_upload_files

router = APIRouter(tags=["corrections"])
teacher = APIRouter(dependencies=[Depends(require_teacher)])


@router.post("/api/student/assignments/{caid}/corrections", status_code=201)
async def student_submit(caid: int, request: Request, q_id: str = Form(...), reason: str = Form("other"),
                         text: Optional[str] = Form(None), photo: Optional[UploadFile] = File(None),
                         student: dict = Depends(require_student), db=Depends(get_db), storage=Depends(get_storage), jobs=Depends(get_jobs)):
    check_content_length(request)
    rows = await run_in_threadpool(_visible, db, student, caid)
    # The student's own "feedback ready" predicate: a marked script in a released assignment.
    if (not rows or rows[0]["submission_id"] is None
            or _status({"status": rows[0]["sub_status"]}, rows[0]["status"] == "released") != "feedback_ready"):
        raise ApiError(404, "not_found", "No released feedback to correct")
    ca = await run_in_threadpool(get_class_assignment, db, student["class_id"], caid)
    detail = await run_in_threadpool(get_submission, db, jobs, rows[0]["submission_id"])
    if detail is None:
        raise ApiError(404, "not_found", "No released feedback to correct")
    payload = (await read_upload_files(request, [photo]))[0] if photo is not None else None
    row = await run_in_threadpool(submit_correction, db, storage, jobs, ca=ca, submission_detail=detail, q_id=q_id,
                                  reason=reason, text=text, photo=payload)
    return JSONResponse({"id": row["id"], "q_id": row["q_id"], "status": row["status"]}, status_code=201)


class OverrideBody(BaseModel):
    total: float


class RejectBody(BaseModel):
    reason: str = ""


@teacher.get("/api/review/corrections")
def index(class_assignment_id: int, db=Depends(get_db)):
    return list_corrections(db, class_assignment_id)


@teacher.post("/api/corrections/{correction_id}/accept")
def accept(correction_id: int, db=Depends(get_db)):
    return decide(db, correction_id, "accept")


@teacher.post("/api/corrections/{correction_id}/override")
def override(correction_id: int, body: OverrideBody, db=Depends(get_db)):
    return decide(db, correction_id, "override", total=body.total)


@teacher.post("/api/corrections/{correction_id}/reject")
def reject(correction_id: int, body: RejectBody, db=Depends(get_db)):
    return decide(db, correction_id, "reject", reason=body.reason)


@teacher.post("/api/class-assignments/{caid}/release-corrections")
def release(caid: int, db=Depends(get_db)):
    return {"released": release_corrections(db, caid)}


router.include_router(teacher)
