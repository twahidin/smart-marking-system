from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from sms.web.deps import COOKIE, client_ip, get_db, issue_session, require_teacher
from sms.web.errors import ApiError
from sms.web.services.setup import MIN_PASSWORD, check_password, needs_setup, password_source, set_password, weak

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


class ChangePasswordBody(BaseModel):
    current: str
    new: str


@router.post("/login", status_code=204)
def login(body: LoginBody, request: Request, response: Response, db=Depends(get_db)):
    ip = client_ip(request)
    limiter = request.app.state.login_limiter
    if limiter.blocked(ip):
        raise ApiError(429, "too_many_attempts", "Too many attempts — wait a minute and try again")
    env_password = request.app.state.config.teacher_password
    if needs_setup(env_password, db):
        raise ApiError(409, "needs_setup", "Smart Marking has not been set up yet — open /setup to create the password")
    if not check_password(env_password, db, body.password):
        limiter.record_failure(ip)
        raise ApiError(401, "bad_password", "That password is not right")
    issue_session(request, response)
    # Return None: FastAPI then sends the injected `response` (with the cookie) as a 204.
    # Returning a new Response object here would DROP the cookie.
    return None


@router.post("/logout", status_code=204)
def logout(response: Response, _: None = Depends(require_teacher)):
    response.delete_cookie(COOKIE, path="/")
    return None


@router.get("/me")
def me(request: Request, db=Depends(get_db), _: None = Depends(require_teacher)):
    return {"authenticated": True, "password_source": password_source(request.app.state.config.teacher_password, db)}


@router.put("/password", status_code=204)
def change_password(body: ChangePasswordBody, request: Request, db=Depends(get_db), _: None = Depends(require_teacher)):
    env_password = request.app.state.config.teacher_password
    if env_password:
        raise ApiError(409, "password_from_env", "The password is set by the TEACHER_PASSWORD variable on Railway — change it there")
    if not check_password(env_password, db, body.current):
        raise ApiError(401, "bad_password", "That password is not right")
    if weak(body.new):
        raise ApiError(400, "weak_password", f"Use at least {MIN_PASSWORD} characters")
    set_password(db, body.new)
    return None
