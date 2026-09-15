from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request):
    try:
        request.app.state.db.query("SELECT 1 AS one")
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"db": f"error: {e}", "worker_last_seen": None})
    return {"db": "ok", "worker_last_seen": request.app.state.jobs.last_heartbeat()}
