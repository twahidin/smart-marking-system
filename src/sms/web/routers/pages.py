from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from sms.web.deps import get_db, get_storage, require_teacher
from sms.web.errors import ApiError

router = APIRouter(prefix="/api/pages", tags=["pages"], dependencies=[Depends(require_teacher)])


@router.get("/{page_id}")
def page(page_id: int, db=Depends(get_db), storage=Depends(get_storage)):
    rows = db.query("SELECT storage_path FROM pages WHERE id = :id", {"id": page_id})
    if not rows:
        raise ApiError(404, "not_found", "No such page")
    path = storage.abs(rows[0]["storage_path"])
    if not path.is_file():
        raise ApiError(404, "not_found", "Page image is missing from storage")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})
