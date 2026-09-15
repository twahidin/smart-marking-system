import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sms.storage import MAX_UPLOAD_BYTES
from sms.web.deps import get_db, get_storage, require_teacher
from sms.web.errors import ApiError
from sms.web.routers.submissions import _read_capped
from sms.web.services.assignments import (
    attach_paper, create_template, delete_template, export_templates, import_templates, list_templates,
    update_template,
)

router = APIRouter(prefix="/api/assignments", tags=["assignments"], dependencies=[Depends(require_teacher)])


class TemplateBody(BaseModel):
    title: str
    subject: str
    context: str = ""
    rubric: Dict[str, Any]
    scheme_kind: str = "criteria"
    questions: Optional[Any] = None
    scheme: Optional[Any] = None
    paper_page_ids: Optional[Any] = None


def _kwargs(body: TemplateBody) -> dict:
    return dict(title=body.title, subject=body.subject, context=body.context, rubric_json=json.dumps(body.rubric),
                scheme_kind=body.scheme_kind, questions=body.questions, scheme=body.scheme,
                paper_page_ids=body.paper_page_ids)


@router.get("")
def index(db=Depends(get_db)):
    return list_templates(db)


@router.post("", status_code=201)
def create(body: TemplateBody, db=Depends(get_db)):
    return create_template(db, **_kwargs(body))


# Declared before /{template_id} so "export" is never parsed as an id.
@router.get("/export")
def export(db=Depends(get_db)):
    return JSONResponse(content=export_templates(db),
                        headers={"Content-Disposition": 'attachment; filename="assignments.json"'})


@router.post("/import")
def import_(payload: Any = Body(...), db=Depends(get_db)):
    return {"created": import_templates(db, payload)}


@router.put("/{template_id}")
def update(template_id: int, body: TemplateBody, db=Depends(get_db)):
    return update_template(db, template_id, **_kwargs(body))


@router.delete("/{template_id}", status_code=204)
def delete(template_id: int, db=Depends(get_db)):
    delete_template(db, template_id)
    return Response(status_code=204)


@router.post("/{template_id}/paper")
async def upload_paper(template_id: int, request: Request, files: List[UploadFile] = File(...),
                       db=Depends(get_db), storage=Depends(get_storage)):
    """Attach the question paper's pages to a template (replacing any previous paper)."""
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "too_large", "Upload is over 50 MB")
    payload = []
    total = 0
    for f in files:
        data = await _read_capped(f, MAX_UPLOAD_BYTES - total)
        total += len(data)
        payload.append((f.filename or "upload", data))
    pages = await run_in_threadpool(attach_paper, db, storage, template_id, payload)
    return {"pages": pages}
