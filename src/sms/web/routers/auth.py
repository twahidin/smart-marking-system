from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from sms.web.deps import COOKIE, SESSION_MAX_AGE, require_teacher
from sms.web.errors import ApiError

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    password: str


@router.post("/login", status_code=204)
def login(body: LoginBody, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    limiter = request.app.state.login_limiter
    if limiter.blocked(ip):
        raise ApiError(429, "too_many_attempts", "Too many attempts — wait a minute and try again")
    if body.password != request.app.state.config.teacher_password:
        limiter.record_failure(ip)
        raise ApiError(401, "bad_password", "That password is not right")
    secure = request.url.hostname not in ("localhost", "127.0.0.1", "testserver")
    response.set_cookie(COOKIE, request.app.state.signer.issue(), max_age=SESSION_MAX_AGE,
                        httponly=True, samesite="lax", secure=secure, path="/")
    # Return None: FastAPI then sends the injected `response` (with the cookie) as a 204.
    # Returning a new Response object here would DROP the cookie.
    return None


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return None


@router.get("/me")
def me(_: None = Depends(require_teacher)):
    return {"authenticated": True}
