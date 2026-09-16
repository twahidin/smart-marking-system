from typing import List, Optional

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from sms.web.deps import get_db, get_jobs, get_settings_store, get_storage, require_teacher
from sms.web.errors import ApiError
from sms.web.services.class_assignments import (delete_class_assignment, get_student, hand_in, list_class_assignments,
                                                marks_csv, release, remove_hand_in, require_class_assignment, roster,
                                                set_assignment, slug, update_class_assignment)
from sms.web.uploads import check_content_length, read_upload_files

router = APIRouter(prefix="/api/classes/{class_id}/assignments", tags=["class-assignments"],
                   dependencies=[Depends(require_teacher)])


class SetBody(BaseModel):
    template_id: int
    title: Optional[str] = None
    due_at: Optional[str] = None
    allow_student_uploads: bool = True


class EditBody(BaseModel):
    title: str
    due_at: Optional[str] = None
    allow_student_uploads: bool = True
    status: str


@router.get("")
def index(class_id: int, db=Depends(get_db)):
    return list_class_assignments(db, class_id)


@router.post("", status_code=201)
def create(class_id: int, body: SetBody, db=Depends(get_db)):
    return set_assignment(db, class_id, template_id=body.template_id, title=body.title, due_at=body.due_at,
                          allow_student_uploads=body.allow_student_uploads)


@router.get("/{caid}")
def show(class_id: int, caid: int, db=Depends(get_db)):
    ca = require_class_assignment(db, class_id, caid)
    return {**ca, "roster": roster(db, ca)}


@router.post("/{caid}/release")
def release_feedback(class_id: int, caid: int, db=Depends(get_db)):
    return release(db, class_id, caid)


@router.get("/{caid}/marks.csv")
async def marks(class_id: int, caid: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    ca = require_class_assignment(db, class_id, caid)
    # One detail read per script; keep the loop off the event loop for a large class.
    text = await run_in_threadpool(marks_csv, db, jobs, ca)
    return Response(content=text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{slug(ca["title"])}-marks.csv"'})


@router.put("/{caid}")
def edit(class_id: int, caid: int, body: EditBody, db=Depends(get_db)):
    return update_class_assignment(db, class_id, caid, title=body.title, due_at=body.due_at,
                                   allow_student_uploads=body.allow_student_uploads, status=body.status)


@router.delete("/{caid}", status_code=204)
def delete(class_id: int, caid: int, db=Depends(get_db)):
    delete_class_assignment(db, class_id, caid)
    return Response(status_code=204)


@router.post("/{caid}/students/{student_id}/upload", status_code=202)
async def upload_for_student(class_id: int, caid: int, student_id: int, request: Request,
                             files: List[UploadFile] = File(...), db=Depends(get_db), storage=Depends(get_storage),
                             jobs=Depends(get_jobs), settings=Depends(get_settings_store)):
    check_content_length(request)
    ca = require_class_assignment(db, class_id, caid)
    student = get_student(db, class_id, student_id)
    if student is None:
        raise ApiError(404, "not_found", "No such student in this class")
    if not await run_in_threadpool(lambda: settings.load().has_key):
        raise ApiError(400, "no_key", "Add an API key under Settings before marking")
    payload = await read_upload_files(request, files)
    # PDF rasterising and image normalising are CPU-bound; keep them off the event loop.
    return await run_in_threadpool(hand_in, db, storage, jobs, ca=ca, student=student, files=payload, source="teacher")


@router.delete("/{caid}/students/{student_id}/submission", status_code=204)
def remove(class_id: int, caid: int, student_id: int, db=Depends(get_db), storage=Depends(get_storage)):
    require_class_assignment(db, class_id, caid)
    remove_hand_in(db, storage, caid, student_id)
    return Response(status_code=204)
