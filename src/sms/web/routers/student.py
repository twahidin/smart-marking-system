from typing import List

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sms.web.deps import (SESSION_MAX_AGE, STUDENT_COOKIE, client_ip, get_db, get_jobs, get_settings_store, get_storage,
                          require_student)
from sms.web.errors import ApiError
from sms.web.services.student import (MAX_HAND_IN_PAGES, TOO_MANY_PAGES, lookup_student, open_for_hand_in, public,
                                      student_assignment, student_assignments, student_hand_in, student_page_path,
                                      touch_last_seen)
from sms.web.uploads import check_content_length, read_upload_files

router = APIRouter(prefix="/api/student", tags=["student"])


class IdBody(BaseModel):
    code: str
    reg_no: int


def _lookup(request: Request, body: IdBody, db):
    ip = client_ip(request)
    limiter = request.app.state.login_limiter
    if limiter.blocked(ip):
        raise ApiError(429, "too_many_attempts", "Too many attempts — wait a minute and try again")
    try:
        return lookup_student(db, body.code, body.reg_no)
    except ApiError:
        limiter.record_failure(ip)
        raise


@router.post("/lookup")
def lookup(body: IdBody, request: Request, db=Depends(get_db)):
    return public(_lookup(request, body, db))


@router.post("/session", status_code=204)
def start_session(body: IdBody, request: Request, response: Response, db=Depends(get_db)):
    found = _lookup(request, body, db)
    touch_last_seen(db, found["student_id"])
    secure = request.url.hostname not in ("localhost", "127.0.0.1", "testserver")
    response.set_cookie(STUDENT_COOKIE, request.app.state.signer.issue_student(found["class_id"], found["student_id"]),
                        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax", secure=secure, path="/")
    return None   # keep the injected response (and its cookie); a new Response would drop it


@router.delete("/session", status_code=204)
def end_session(response: Response):
    response.delete_cookie(STUDENT_COOKIE, path="/")
    return None


@router.get("/me")
def me(student: dict = Depends(require_student)):
    return {"class_name": student["class_name"], "code": student["code"], "student_name": student["name"], "reg_no": student["reg_no"]}


@router.get("/assignments")
def assignments(student: dict = Depends(require_student), db=Depends(get_db)):
    return student_assignments(db, student)


@router.get("/assignments/{caid}")
def assignment(caid: int, student: dict = Depends(require_student), db=Depends(get_db), jobs=Depends(get_jobs)):
    return student_assignment(db, jobs, student, caid)


@router.post("/assignments/{caid}/hand-in", status_code=202)
async def hand_in_pages(caid: int, request: Request, files: List[UploadFile] = File(...),
                        student: dict = Depends(require_student), db=Depends(get_db), storage=Depends(get_storage),
                        jobs=Depends(get_jobs), settings=Depends(get_settings_store)):
    check_content_length(request)
    # Cheap file-count cap before reading the body; the page cap (PDFs rasterise to many pages) is
    # enforced again inside student_hand_in.
    if len(files) > MAX_HAND_IN_PAGES:
        raise ApiError(400, "too_many_pages", TOO_MANY_PAGES)
    # Draft -> 404 and closed -> 403 before anything about the teacher's setup, as the teacher route does.
    await run_in_threadpool(open_for_hand_in, db, student, caid)
    if not await run_in_threadpool(lambda: settings.load().has_key):
        raise ApiError(400, "no_key", "Your teacher has not finished setting up marking yet — try again later")
    payload = await read_upload_files(request, files)
    # PDF rasterising and image normalising are CPU-bound; keep them off the event loop.
    return await run_in_threadpool(student_hand_in, db, storage, jobs, student, caid, payload)


@router.get("/pages/{page_id}")
def page(page_id: int, student: dict = Depends(require_student), db=Depends(get_db), storage=Depends(get_storage)):
    return FileResponse(student_page_path(db, storage, student, page_id), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})
