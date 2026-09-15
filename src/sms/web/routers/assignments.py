import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sms.web.deps import get_db, get_storage, require_teacher
from sms.web.services.assignments import (
    attach_paper, create_template, delete_template, duplicate_template, export_templates, import_templates,
    list_templates, update_template,
)
from sms.web.uploads import read_upload_files

router = APIRouter(prefix="/api/assignments", tags=["assignments"], dependencies=[Depends(require_teacher)])


class TemplateBody(BaseModel):
    title: str
    subject: str
    context: str = ""
    rubric: Dict[str, Any]
    scheme_kind: str = "criteria"
    questions: Optional[Any] = None
    scheme: Optional[Any] = None
    delete_pages_after_marking: Optional[bool] = None


def _kwargs(body: TemplateBody) -> dict:
    return dict(title=body.title, subject=body.subject, context=body.context, rubric_json=json.dumps(body.rubric),
                scheme_kind=body.scheme_kind, questions=body.questions, scheme=body.scheme,
                delete_pages_after_marking=body.delete_pages_after_marking)


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


@router.post("/{template_id}/duplicate", status_code=201)
def duplicate(template_id: int, db=Depends(get_db)):
    return duplicate_template(db, template_id)


@router.post("/{template_id}/paper")
async def upload_paper(template_id: int, request: Request, files: List[UploadFile] = File(...),
                       db=Depends(get_db), storage=Depends(get_storage)):
    """Attach the question paper's pages to a template (replacing any previous paper)."""
    payload = await read_upload_files(request, files)
    pages = await run_in_threadpool(attach_paper, db, storage, template_id, payload)
    return {"pages": pages}
