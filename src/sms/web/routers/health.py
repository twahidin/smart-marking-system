import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("sms.web")

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request):
    try:
        request.app.state.db.query("SELECT 1 AS one")
    except Exception:  # noqa: BLE001
        log.exception("health check: db query failed")
        return JSONResponse(status_code=503, content={"db": "error", "worker_last_seen": None})
    return {"db": "ok", "worker_last_seen": request.app.state.jobs.last_heartbeat()}
