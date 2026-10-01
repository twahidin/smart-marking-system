from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from sms.providers.registry import get_provider
from sms.web.deps import get_db, get_settings_store, issue_session
from sms.web.errors import ApiError
from sms.web.services.setup import MIN_PASSWORD, needs_setup, set_password, weak

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupBody(BaseModel):
    password: str
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


@router.get("/status")
def status(request: Request, db=Depends(get_db)):
    return {"needs_setup": needs_setup(request.app.state.config.teacher_password, db)}


@router.post("", status_code=204)
def run_setup(body: SetupBody, request: Request, response: Response, db=Depends(get_db), store=Depends(get_settings_store)):
    """One shot: creates the teacher password (and optionally connects a model), then signs the caller in."""
    if not needs_setup(request.app.state.config.teacher_password, db):
        raise ApiError(409, "already_set_up", "Smart Marking is already set up — sign in instead")
    if weak(body.password):
        raise ApiError(400, "weak_password", f"Use at least {MIN_PASSWORD} characters")
    spec = None
    if body.provider:
        try:
            spec = get_provider(body.provider)
        except KeyError:
            raise ApiError(400, "bad_provider", "Unknown provider")
    # Everything validated: the password first (the thing the wizard exists for), then the model.
    set_password(db, body.password)
    if spec is not None:
        s = store.load()
        s.provider = spec.id
        s.model = (body.model or "").strip() or spec.default_model
        s.api_key = (body.api_key or "").strip() or None
        s.rpm_limit = spec.default_rpm
        store.save(s)
    issue_session(request, response)
    return None
