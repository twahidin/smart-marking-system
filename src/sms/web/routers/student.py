from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from sms.web.deps import SESSION_MAX_AGE, STUDENT_COOKIE, client_ip, get_db, require_student
from sms.web.errors import ApiError
from sms.web.services.student import lookup_student, public, touch_last_seen

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
