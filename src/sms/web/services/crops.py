"""Answer crops: the region of a photographed page each marked part came from.

The page reader returns, per part, the page it starts on and a box (fractions of the page). At
marking time the region is cut out — padded, because boxes are approximate — and stored as a
small JPEG that outlives the page when retention is 'crops'. A part with no usable box keeps the
whole page as its crop; an unlocated part (no page, or a page index the script does not have)
gets none."""
import io
import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image

from sms.memory.db import Database
from sms.schemas.extraction import ExtractedScript
from sms.storage import PageStorage

log = logging.getLogger("sms.crops")

PAD = 0.08        # of the box's own width / height, each side
MIN_PAD = 0.02    # of the page's width / height — thin boxes still get breathing room
MIN_AREA = 0.01   # of the page; anything smaller is treated as "no box"
JPEG_QUALITY = 85


@dataclass
class PartCrop:
    q_id: str
    page_index: int
    box: Optional[List[float]]    # the box as the reader gave it; None when the whole page was kept
    whole_page: bool
    storage_path: str
    sha256: str
    width: int
    height: int


def crop_box(page_w: int, page_h: int, box: Optional[Sequence[float]]) -> Optional[Tuple[int, int, int, int]]:
    """Pixel rectangle to cut for a fractional box, padded and snapped to the page; None when the box
    is missing, inverted, outside the page or too small to be a real answer region."""
    if not box or len(box) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1) or (x1 - x0) * (y1 - y0) < MIN_AREA:
        return None
    bw, bh = (x1 - x0) * page_w, (y1 - y0) * page_h
    px, py = max(PAD * bw, MIN_PAD * page_w), max(PAD * bh, MIN_PAD * page_h)
    return (max(0, round(x0 * page_w - px)), max(0, round(y0 * page_h - py)),
            min(page_w, round(x1 * page_w + px)), min(page_h, round(y1 * page_h + py)))


def crop_parts(storage: PageStorage, pages: List[bytes], extracted: ExtractedScript) -> List[PartCrop]:
    """One crop per located part, in extraction order. Never raises for a bad box or page: those parts
    simply get no crop."""
    out: List[PartCrop] = []
    opened: dict = {}
    for q in extracted.questions:
        if q.page is None or not (0 <= q.page < len(pages)):
            continue
        if q.page not in opened:
            try:
                opened[q.page] = Image.open(io.BytesIO(pages[q.page])).convert("RGB")
            except Exception as e:  # noqa: BLE001
                log.warning("could not open page %s for cropping: %s", q.page, e)
                opened[q.page] = None
        im = opened[q.page]
        if im is None:
            continue
        rect = crop_box(im.width, im.height, q.box)
        region = im.crop(rect) if rect else im
        buf = io.BytesIO(); region.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
        digest, rel = storage.put_crop(buf.getvalue())
        out.append(PartCrop(q_id=q.q_id, page_index=q.page, box=list(q.box) if rect else None, whole_page=rect is None,
                            storage_path=rel, sha256=digest, width=region.width, height=region.height))
    return out


def store_part_crops(db: Database, submission_id: int, crops: List[PartCrop]) -> None:
    """Replace the submission's crops (a re-mark produces a fresh set). Rows of the previous set are
    deleted outright; their files are content-addressed and may be shared, so they are left on disk
    for the cleanup paths that check references."""
    with db.transaction() as tx:
        tx.execute("DELETE FROM part_crops WHERE submission_id = :s", {"s": submission_id})
        for c in crops:
            tx.execute("INSERT INTO part_crops (submission_id, q_id, page_index, box_json, whole_page, storage_path, sha256, width, height) "
                       "VALUES (:s, :q, :p, :b, :w, :path, :h, :wd, :ht)",
                       {"s": submission_id, "q": c.q_id, "p": c.page_index, "b": json.dumps(c.box) if c.box else None,
                        "w": c.whole_page, "path": c.storage_path, "h": c.sha256, "wd": c.width, "ht": c.height})


def crops_for_submission(db: Database, submission_id: int) -> dict:
    """{q_id: {id, storage_path, whole_page, page_index}} for the undeleted crops of a submission."""
    rows = db.query("SELECT id, q_id, storage_path, whole_page, page_index FROM part_crops "
                    "WHERE submission_id = :s AND deleted_at IS NULL ORDER BY id", {"s": submission_id})
    return {r["q_id"]: {"id": r["id"], "storage_path": r["storage_path"], "whole_page": bool(r["whole_page"]),
                        "page_index": r["page_index"]} for r in rows}
