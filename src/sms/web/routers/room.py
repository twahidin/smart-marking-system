import asyncio
import time
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from sms.web.deps import get_db, require_teacher
from sms.web.services.room import events_after, room_snapshot, sse_line, thoughts

router = APIRouter(tags=["room"], dependencies=[Depends(require_teacher)])
POLL_S = 2.0
HEARTBEAT_S = 15.0


@router.get("/api/room")
def snapshot(class_assignment_id: Optional[int] = None, db=Depends(get_db)):
    return room_snapshot(db, class_assignment_id)


@router.get("/api/room/events")
async def events(request: Request, after: int = Query(0, ge=0), class_assignment_id: Optional[int] = None,
                 once: int = Query(0), last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
                 db=Depends(get_db)):
    """Server-Sent Events: every started/finished stage event after `after` (or the Last-Event-ID
    header), polled from the database every 2 s with a comment heartbeat every 15 s. The loop is async,
    so an idle stream holds no thread; it ends when the client disconnects. `once=1` returns after the
    first poll — for tests and for a client that prefers polling."""
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    async def gen() -> AsyncIterator[str]:
        nonlocal cursor
        last_beat = time.monotonic()
        while True:
            batch = await run_in_threadpool(events_after, db, cursor, class_assignment_id)
            for e in batch:
                cursor = e["id"]
                yield sse_line(e)
            if once:
                return
            if time.monotonic() - last_beat > HEARTBEAT_S:
                last_beat = time.monotonic()
                yield ": ping\n\n"
            await asyncio.sleep(POLL_S)
            if await request.is_disconnected():
                return

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/api/submissions/{submission_id}/thoughts")
def submission_thoughts(submission_id: int, db=Depends(get_db)):
    return thoughts(db, submission_id)
