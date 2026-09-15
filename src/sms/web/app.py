import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sms.memory.db import Database
from sms.providers.crypto import KeyCipher
from sms.providers.settings import SettingsStore
from sms.storage import PageStorage
from sms.web.config import AppConfig
from sms.web.deps import LoginLimiter, SessionSigner
from sms.web.errors import install_error_handlers
from sms.web.routers import assignments, auth, health, learning, pages, queue, records, settings, submissions
from sms.worker.jobs import JobStore
from sms.worker.worker import Worker

log = logging.getLogger("sms.web")


def mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA: /assets/* statically, everything else -> index.html (except /api)."""
    if not (dist / "index.html").exists():
        log.warning("SPA not built at %s — API only", dist)
        return
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    root = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str, request: Request):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": "No such route"}})
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


def create_app(config: AppConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings_store.ensure_seeded(config.env)
        stop = threading.Event()
        thread: Optional[threading.Thread] = None
        if config.embedded_worker:
            thread = Worker(app.state.db, app.state.storage, app.state.settings_store).start_thread(stop)
        try:
            yield
        finally:
            stop.set()
            if thread:
                thread.join(timeout=5)
            app.state.db.dispose()

    app = FastAPI(title="Smart Marking", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.config = config
    app.state.db = Database(url=config.database_url)
    app.state.settings_store = SettingsStore(app.state.db, KeyCipher(config.secret_key))
    app.state.storage = PageStorage(config.storage_dir)
    app.state.jobs = JobStore(app.state.db)
    app.state.signer = SessionSigner(config.secret_key)
    app.state.login_limiter = LoginLimiter()
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(settings.router)
    app.include_router(records.router)  # before submissions: POST /api/submissions/records.zip vs /{submission_id}
    app.include_router(submissions.router)
    app.include_router(assignments.router)
    app.include_router(pages.router)
    app.include_router(queue.router)
    app.include_router(learning.router)
    if config.static_dir:
        mount_spa(app, config.static_dir)
    return app


def app_from_env() -> FastAPI:
    return create_app(AppConfig.from_env())
