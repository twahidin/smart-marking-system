from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel

from sms.web.deps import get_db, require_teacher
from sms.web.errors import ApiError
from sms.web.services.classes import (create_class, get_class, list_classes, regenerate_code, rename_class,
                                      set_archived)
from sms.web.services.classlist import list_students, parse_classlist, replace_classlist
from sms.web.uploads import read_upload_files

router = APIRouter(prefix="/api/classes", tags=["classes"], dependencies=[Depends(require_teacher)])


class ClassBody(BaseModel):
    name: str


class ClasslistBody(BaseModel):
    rows: List[Dict[str, Any]]


@router.get("")
def index(db=Depends(get_db)):
    return list_classes(db)


@router.post("", status_code=201)
def create(body: ClassBody, db=Depends(get_db)):
    return create_class(db, body.name)


@router.get("/{class_id}")
def show(class_id: int, db=Depends(get_db)):
    c = get_class(db, class_id)
    if c is None:
        raise ApiError(404, "not_found", "No such class")
    return c


@router.put("/{class_id}")
def rename(class_id: int, body: ClassBody, db=Depends(get_db)):
    return rename_class(db, class_id, body.name)


@router.post("/{class_id}/archive")
def archive(class_id: int, db=Depends(get_db)):
    return set_archived(db, class_id, True)


@router.post("/{class_id}/unarchive")
def unarchive(class_id: int, db=Depends(get_db)):
    return set_archived(db, class_id, False)


@router.post("/{class_id}/regenerate-code")
def regenerate(class_id: int, db=Depends(get_db)):
    return regenerate_code(db, class_id)


@router.post("/{class_id}/students/preview")
async def preview_students(class_id: int, request: Request, file: UploadFile = File(...), db=Depends(get_db)):
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    payload = await read_upload_files(request, [file])
    rows, errors = parse_classlist(payload[0][1] if payload else b"")
    return {"rows": rows, "errors": errors}


@router.put("/{class_id}/students")
def put_students(class_id: int, body: ClasslistBody, db=Depends(get_db)):
    return replace_classlist(db, class_id, body.rows)


@router.get("/{class_id}/students")
def students(class_id: int, db=Depends(get_db)):
    if get_class(db, class_id) is None:
        raise ApiError(404, "not_found", "No such class")
    return list_students(db, class_id)
