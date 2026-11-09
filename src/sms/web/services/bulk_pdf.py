"""One combined PDF of a class's scripts -> one hand-in per student.

A school scanner turns a pile of exam booklets into a single PDF: every booklet starts with the same printed
cover (name, index number, class), and each PDF page is often an A3 spread of two booklet pages. This module
finds the booklets by comparing every page with the first cover, reads each cover's index number and name with
the assignment's reading model, and matches the booklet to a student. Nothing is handed in until the teacher
confirms the matches (`bulk_pdf_commit`), which re-reads the same PDF with the page ranges they confirmed.
"""
import base64
import io
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PIL import Image
from pydantic import BaseModel, Field

from sms.memory.db import Database
from sms.storage import MAX_LONG_EDGE, PageStorage
from sms.web.errors import ApiError
from sms.web.services.class_assignments import _bulk_handed_in_ids, hand_in, remove_hand_in
from sms.web.services.classlist import list_students
from sms.worker.jobs import JobStore

log = logging.getLogger(__name__)

MAX_PDF_PAGES = 400
SPREAD_RATIO = 1.2         # a page this much wider than tall is a two-page spread
COVER_MIN_SCORE = 0.45     # correlation with the first cover; covers scored 0.56-1.0, other pages <= 0.33
BLANK_INK = 0.01           # pixels darker than their surroundings; blank pages scored <= 0.006, written ones >= 0.03
SIG_SIZE = (70, 100)       # the coarse layout signature a page half is compared on
COVER_READERS = 4


class CoverInfo(BaseModel):
    """What the reading model copies off a booklet's cover."""
    index_number: Optional[str] = Field(None, description="The index or register number written on the cover, digits only; null if blank or unreadable")
    name: Optional[str] = Field(None, description="The student's name as written on the cover; null if blank or unreadable")


@dataclass
class Booklet:
    start: int       # 1-based first PDF page
    end: int         # 1-based last PDF page, inclusive
    cover_half: int  # which half of the first page is the cover: 0 = whole page or left, 1 = right


# --- reading the PDF -----------------------------------------------------------------------------

def open_pdf(pdf_bytes: bytes):
    import pymupdf as fitz
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        raise ApiError(400, "bad_file", "That file isn't a readable PDF")
    if doc.needs_pass:
        raise ApiError(400, "bad_file", "That PDF is password-protected — save an unlocked copy and try again")
    if len(doc) == 0:
        raise ApiError(400, "bad_file", "That PDF has no pages")
    if len(doc) > MAX_PDF_PAGES:
        raise ApiError(400, "too_large", f"That PDF has {len(doc)} pages; the most one upload can take is {MAX_PDF_PAGES}")
    return doc


def _is_spread(page) -> bool:
    r = page.rect
    return r.width > r.height * SPREAD_RATIO


def _render(page, dpi: float, gray: bool = False, clip=None) -> Image.Image:
    import pymupdf as fitz
    pix = page.get_pixmap(dpi=int(dpi), colorspace=fitz.csGRAY if gray else fitz.csRGB, alpha=False, clip=clip)
    return Image.frombytes("L" if gray else "RGB", (pix.width, pix.height), pix.samples)


def _halves(page, img: Image.Image) -> List[Image.Image]:
    if not _is_spread(page):
        return [img]
    w, h = img.size
    return [img.crop((0, 0, w // 2, h)), img.crop((w // 2, 0, w, h))]


def _signature(img: Image.Image) -> List[float]:
    px = list(img.convert("L").resize(SIG_SIZE).tobytes())
    mean = sum(px) / len(px)
    sd = math.sqrt(sum((p - mean) ** 2 for p in px) / len(px)) or 1.0
    return [(p - mean) / sd for p in px]


def _ink(img: Image.Image) -> float:
    """Fraction of pixels noticeably darker than their surroundings: print and handwriting count, the smooth grey
    of a scanner's shadow or the page's own tint does not. Measured at a fixed working size, so it doesn't depend
    on the resolution the page was rendered at."""
    from PIL import ImageChops, ImageFilter
    g = img.convert("L")
    small = g.resize((400, max(1, round(g.height * 400 / g.width))), Image.BILINEAR)
    background = small.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.BoxBlur(4))
    hist = ImageChops.subtract(background, small).histogram()
    return sum(hist[48:]) / max(1, small.width * small.height)


def find_booklets(doc) -> List[Booklet]:
    """Split the PDF wherever a page looks like the first page's cover. The cover half of the first page is the
    one with more ink (a scanned spread usually pairs the cover with a blank back page)."""
    halves = [_halves(p, _render(p, 24, gray=True)) for p in doc]
    first = halves[0]
    cover_side = max(range(len(first)), key=lambda i: _ink(first[i]))
    ref = _signature(first[cover_side])
    starts: List[Tuple[int, int]] = [(0, cover_side)]
    for i in range(1, len(halves)):
        scores = [sum(a * b for a, b in zip(_signature(h), ref)) / len(ref) for h in halves[i]]
        best = max(range(len(scores)), key=lambda k: scores[k])
        if scores[best] >= COVER_MIN_SCORE:
            starts.append((i, best))
    out = []
    for n, (i, side) in enumerate(starts):
        end = starts[n + 1][0] - 1 if n + 1 < len(starts) else len(halves) - 1
        out.append(Booklet(start=i + 1, end=end + 1, cover_half=side))
    return out


def booklet_pages(doc, b: Booklet) -> List[Tuple[str, bytes]]:
    """The booklet as page images for marking: spreads split into their two pages, rendered so each page's long
    edge is about the app's 2,000-pixel cap, and blank pages dropped."""
    out: List[Tuple[str, bytes]] = []
    for pno in range(b.start - 1, b.end):
        page = doc[pno]
        r = page.rect
        unit_long = max(r.width / 2, r.height) if _is_spread(page) else max(r.width, r.height)
        dpi = int(min(220, MAX_LONG_EDGE * 72 / unit_long))
        for k, half in enumerate(_halves(page, _render(page, dpi))):
            if _ink(half) < BLANK_INK:
                continue
            buf = io.BytesIO()
            half.save(buf, format="JPEG", quality=85)
            out.append((f"p{pno + 1:03d}{'ab'[k] if _is_spread(page) else ''}.jpg", buf.getvalue()))
    return out


def cover_header(doc, b: Booklet, width: int = 900) -> bytes:
    """The top third of the booklet's cover, where the name and index number are written, as a JPEG about
    `width` pixels across: only that strip is rendered, so this stays quick for a whole class."""
    import pymupdf as fitz
    page = doc[b.start - 1]
    r = page.rect
    x0 = r.x0 + (r.width / 2 if _is_spread(page) and b.cover_half == 1 else 0)
    x1 = x0 + (r.width / 2 if _is_spread(page) else r.width)
    head = _render(page, width * 72 / (x1 - x0), clip=fitz.Rect(x0, r.y0, x1, r.y0 + r.height * 0.32))
    buf = io.BytesIO()
    head.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


# --- reading covers and matching students ---------------------------------------------------------

CoverReader = Callable[[bytes], CoverInfo]

COVER_PROMPT = ("This is the top of a student's exam booklet cover. Copy the index (or register) number and the "
                "student's name exactly as handwritten. Use null for any field that is blank or unreadable.")


def model_cover_reader(settings) -> CoverReader:
    """Reads a cover with the assignment's reading model (its pinned model, else its subject's, else Settings)."""
    import instructor
    from sms.providers.client import build_client
    from sms.providers.ratelimit import TokenBucket
    from sms.providers.registry import get_provider

    client = build_client(settings.provider, settings.api_key, base_url=settings.base_url)
    params = get_provider(settings.provider).api_params or {}
    bucket = TokenBucket(settings.rpm_limit)

    def read(jpg: bytes) -> CoverInfo:
        bucket.acquire()
        b64 = base64.b64encode(jpg).decode()
        image = instructor.Image(source=f"data:image/jpeg;base64,{b64}", media_type="image/jpeg", data=b64)
        return client.chat.completions.create(
            model=settings.effective_extractor_model, response_model=CoverInfo, max_retries=1, timeout=60,
            messages=[{"role": "user", "content": [{"type": "text", "text": COVER_PROMPT}, image]}], **params)
    return read


def _digits(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")


def _tokens(s: Optional[str]) -> List[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def match_student(info: CoverInfo, students: Sequence[dict]) -> Tuple[Optional[int], Optional[str]]:
    """(student id, how) for a cover: its index number, else its last two digits when the class is numbered 1-99
    (an index like 3401 is class 34, register 01), else a unique name match. (None, None) leaves it to the teacher."""
    digits = _digits(info.index_number)
    if digits:
        exact = [s for s in students if int(s["reg_no"]) == int(digits)]
        if len(exact) == 1:
            return exact[0]["id"], "index"
        if len(digits) >= 3 and all(int(s["reg_no"]) < 100 for s in students):
            tail = [s for s in students if int(s["reg_no"]) == int(digits[-2:])]
            if len(tail) == 1:
                return tail[0]["id"], "index"
    want = _tokens(info.name)
    if want:
        named = [s for s in students if _tokens(s["name"]) == want] or \
                [s for s in students if set(want) <= set(_tokens(s["name"]))]
        if len(named) == 1:
            return named[0]["id"], "name"
    return None, None


# --- preview and commit ----------------------------------------------------------------------------

def bulk_pdf_preview(db: Database, ca: Dict[str, Any], pdf_bytes: bytes, read_cover: CoverReader) -> Dict[str, Any]:
    """Split the PDF into booklets and propose a student for each from its cover; nothing is handed in."""
    doc = open_pdf(pdf_bytes)
    booklets = find_booklets(doc)
    students = list_students(db, ca["class_id"])
    handed_in = _bulk_handed_in_ids(db, ca["id"])
    headers = [cover_header(doc, b) for b in booklets]

    errors: List[str] = []

    def read(jpg: bytes) -> CoverInfo:
        try:
            return read_cover(jpg)
        except Exception as e:
            from sms.providers.errors import error_message
            log.exception("reading a booklet cover failed")
            errors.append(error_message(e))
            return CoverInfo(index_number=None, name=None)

    with ThreadPoolExecutor(max_workers=COVER_READERS) as pool:
        infos = list(pool.map(read, headers))
    rows = []
    for n, (b, info, png) in enumerate(zip(booklets, infos, headers), start=1):
        sid, how = match_student(info, students)
        rows.append({"booklet": n, "start": b.start, "end": b.end, "page_count": b.end - b.start + 1,
                     "cover": "data:image/jpeg;base64," + base64.b64encode(png).decode(),
                     "read": info.model_dump(), "student_id": sid, "matched_by": how,
                     "already_handed_in": sid in handed_in if sid else False})
    # A failure on every cover is a setup problem (a bad model id, a spent key), worth telling the teacher.
    return {"booklets": rows, "pdf_pages": len(doc), "read_error": errors[0] if errors and len(errors) == len(headers) else None,
            "students": [{"id": s["id"], "reg_no": s["reg_no"], "name": s["name"], "already_handed_in": s["id"] in handed_in}
                         for s in students]}


def _parse_assignments(raw: List[Dict[str, Any]], page_count: int, students: Dict[int, dict]) -> List[Tuple[Booklet, dict]]:
    out, seen = [], set()
    for a in raw:
        try:
            start, end, sid = int(a["start"]), int(a["end"]), int(a["student_id"])
        except (KeyError, TypeError, ValueError):
            raise ApiError(400, "bad_request", "Each booklet needs a start page, an end page and a student")
        if not 1 <= start <= end <= page_count:
            raise ApiError(400, "bad_request", f"Pages {start}–{end} are outside this {page_count}-page PDF")
        if sid not in students:
            raise ApiError(400, "bad_request", "A booklet is matched to a student who isn't in this class")
        if sid in seen:
            raise ApiError(400, "bad_request", f"#{students[sid]['reg_no']} {students[sid]['name']} is matched to two booklets")
        seen.add(sid)
        out.append((Booklet(start=start, end=end, cover_half=0), students[sid]))
    return out


def bulk_pdf_commit(db: Database, storage: PageStorage, jobs: JobStore, ca: Dict[str, Any], pdf_bytes: bytes,
                    assignments: List[Dict[str, Any]], replace: bool) -> Dict[str, Any]:
    """Hand in each confirmed booklet for its student, in register-number order, with the zip upload's rules: a
    student who already handed in is skipped unless `replace`; one student's failure never stops the rest."""
    doc = open_pdf(pdf_bytes)
    students = {s["id"]: s for s in list_students(db, ca["class_id"])}
    plan = sorted(_parse_assignments(assignments, len(doc), students), key=lambda p: p[1]["reg_no"])
    handed_in = _bulk_handed_in_ids(db, ca["id"])
    created: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for booklet, s in plan:
        already = s["id"] in handed_in
        if already and not replace:
            skipped.append({"reg_no": s["reg_no"]})
            continue
        try:
            files = booklet_pages(doc, booklet)
        except Exception:
            log.exception("rendering booklet pages %s-%s failed", booklet.start, booklet.end)
            failed.append({"reg_no": s["reg_no"], "error": "couldn't read those pages of the PDF"})
            continue
        if not files:
            failed.append({"reg_no": s["reg_no"], "error": f"pages {booklet.start}–{booklet.end} are all blank"})
            continue
        removed = False
        try:
            if already:
                remove_hand_in(db, storage, ca["id"], s["id"])
                removed = True
            hand_in(db, storage, jobs, ca=ca, student=s, files=files, source="teacher")
            created.append({"reg_no": s["reg_no"], "ignored": [], "pages": len(files)})
        except ApiError as e:
            failed.append({"reg_no": s["reg_no"], "error": f"Previous hand-in removed — {e.message}" if removed else e.message})
        except Exception:
            log.exception("bulk PDF hand-in failed for student %s on class assignment %s", s["id"], ca["id"])
            generic = "something went wrong handing this student in"
            failed.append({"reg_no": s["reg_no"], "error": f"Previous hand-in removed — {generic}" if removed else generic})
    return {"created": created, "skipped": skipped, "failed": failed, "unmatched": [], "ambiguous": []}
