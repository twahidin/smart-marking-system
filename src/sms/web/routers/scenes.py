from fastapi import APIRouter, Depends, Query

from sms.web.deps import get_db, require_teacher
from sms.web.services.scenes import due_class_assignments, review_summary

router = APIRouter(tags=["scenes"], dependencies=[Depends(require_teacher)])


@router.get("/api/review/summary")
def summary(db=Depends(get_db)):
    return review_summary(db)


@router.get("/api/class-assignments/due")
def due(days: int = Query(7, ge=0, le=365), db=Depends(get_db)):
    return due_class_assignments(db, days)
