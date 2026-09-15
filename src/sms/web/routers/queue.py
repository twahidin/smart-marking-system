from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sms.web.deps import get_db, require_teacher
from sms.web.services.queue import list_queue, resolve_queue_item

router = APIRouter(prefix="/api/queue", tags=["queue"], dependencies=[Depends(require_teacher)])


class ResolveBody(BaseModel):
    criterion_scores: List[int]
    reason: str = ""


@router.get("")
def index(db=Depends(get_db)):
    return list_queue(db)


@router.post("/{item_id}/resolve")
def resolve(item_id: int, body: ResolveBody, db=Depends(get_db)):
    return resolve_queue_item(db, item_id, body.criterion_scores, body.reason.strip())
