"""Reading multipart page uploads with the 50 MB cap enforced twice: once on the declared
Content-Length (cheap, before any body is read) and again on the bytes actually received."""
from typing import List, Tuple

from fastapi import Request, UploadFile

from sms.storage import MAX_UPLOAD_BYTES
from sms.web.errors import ApiError

_UPLOAD_CHUNK_BYTES = 1024 * 1024


async def _read_capped(f: UploadFile, budget: int) -> bytes:
    """Read an UploadFile in chunks, never materialising more than `budget` bytes."""
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = await f.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > budget:
            raise ApiError(413, "too_large", "Upload is over 50 MB")
        chunks.append(chunk)
    return b"".join(chunks)


def check_content_length(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length is not None and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "too_large", "Upload is over 50 MB")


async def read_upload_files(request: Request, files: List[UploadFile]) -> List[Tuple[str, bytes]]:
    """Return (filename, bytes) for each upload, or raise 413 `too_large` past the cap."""
    check_content_length(request)
    payload: List[Tuple[str, bytes]] = []
    total = 0
    for f in files:
        data = await _read_capped(f, MAX_UPLOAD_BYTES - total)
        total += len(data)
        payload.append((f.filename or "upload", data))
    return payload
