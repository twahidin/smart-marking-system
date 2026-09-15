from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sms.web.deps import get_db, get_storage, require_teacher
from sms.web.services.queue import list_queue, resolve_queue_item

router = APIRouter(prefix="/api/queue", tags=["queue"], dependencies=[Depends(require_teacher)])


class AllocationChoice(BaseModel):
    label: str
    got: bool


class ResolveBody(BaseModel):
    """v1 items: criterion_scores. v2 mark-scheme parts: allocations, or `total` when the part has no
    allocations to tick. v2 rubric criteria: band, plus `marks` (0 .. proposed) for a criterion the
    rubric has no bands for."""

    criterion_scores: Optional[List[int]] = None
    allocations: Optional[List[AllocationChoice]] = None
    band: Optional[str] = None
    total: Optional[int] = None
    marks: Optional[int] = None
    reason: str = ""


@router.get("")
def index(db=Depends(get_db)):
    return list_queue(db)


@router.post("/{item_id}/resolve")
def resolve(item_id: int, body: ResolveBody, db=Depends(get_db), storage=Depends(get_storage)):
    return resolve_queue_item(db, item_id, body.criterion_scores, body.reason.strip(), storage=storage,
                              allocations=[a.model_dump() for a in body.allocations] if body.allocations is not None else None,
                              band=body.band, total=body.total, marks=body.marks)
