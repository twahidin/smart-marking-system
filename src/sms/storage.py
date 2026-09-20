import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Tuple

from PIL import Image, ImageOps, UnidentifiedImageError

# Pillow's default decompression-bomb threshold is ~89 MP (warning) / ~178 MP (error). A phone
# scan of an exam page is well under 50 MP; anything larger is a bomb or a mistake, and decoding
# it would take hundreds of MB of RAM on a small Railway container. Pillow raises
# DecompressionBombError above 2x this value, which _image_from_bytes maps to an UploadError.
Image.MAX_IMAGE_PIXELS = 50_000_000

MAX_LONG_EDGE = 2000
JPEG_QUALITY = 85
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
PDF_EXTS = {".pdf"}


class UploadError(Exception):
    def __init__(self, filename: str, message: str):
        super().__init__(f"{filename}: {message}")
        self.filename = filename
        self.message = message


@dataclass(frozen=True)
class ProcessedPage:
    sha256: str
    storage_path: str
    width: int
    height: int
    source_filename: str


class PageStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "pages").mkdir(parents=True, exist_ok=True)

    def put_jpeg(self, data: bytes) -> Tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        rel = f"pages/{digest}.jpg"
        path = self.root / rel
        if not path.exists():
            # Unique per-call tmp name: two concurrent writers of identical
            # content must not race on the same tmp path.
            tmp = path.with_name(f"{digest}.{uuid.uuid4().hex}.tmp")
            tmp.write_bytes(data)
            try:
                tmp.replace(path)
            except (FileNotFoundError, FileExistsError):
                # Another writer already produced the same content-addressed
                # file; since the path is derived from the content hash, the
                # existing file is equivalent to what we would have written.
                tmp.unlink(missing_ok=True)
        return digest, rel

    def put_file(self, data: bytes, ext: str) -> Tuple[str, str]:
        """Store an uploaded program file (.py / .sb3 / .xlsx) verbatim under `files/<aa>/<sha><ext>`.

        Same content-addressed rules as `put_jpeg` — identical bytes are stored once — but fanned
        out over a first-byte subdirectory: a class set is a dozen files per script, not one page."""
        digest = hashlib.sha256(data).hexdigest()
        rel = f"files/{digest[:2]}/{digest}{ext}"
        path = self.root / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Unique per-call tmp name, as in put_jpeg: two writers of identical content must
            # not race on the same tmp path.
            tmp = path.with_name(f"{digest}.{uuid.uuid4().hex}.tmp")
            tmp.write_bytes(data)
            try:
                tmp.replace(path)
            except (FileNotFoundError, FileExistsError):
                tmp.unlink(missing_ok=True)
        return digest, rel

    def abs(self, relative_path: str) -> Path:
        return self.root / relative_path

    def read(self, relative_path: str) -> bytes:
        return self.abs(relative_path).read_bytes()


_heif_registered = False


def _register_heif() -> None:
    global _heif_registered
    if _heif_registered:
        return
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:  # pragma: no cover
        pass
    finally:
        _heif_registered = True


def _normalise(img: Image.Image) -> Tuple[bytes, int, int]:
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    long_edge = max(w, h)
    if long_edge > MAX_LONG_EDGE:
        scale = MAX_LONG_EDGE / long_edge
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue(), img.size[0], img.size[1]


def _images_from_pdf(filename: str, data: bytes, remaining: int, max_pages: int) -> Iterator[Image.Image]:
    """Open and validate the PDF eagerly, then yield one rasterised page at a time.

    Rendering lazily keeps at most one raw 150-dpi page (~5 MB) alive while the caller
    normalises and stores it, instead of holding a whole 60-page script in memory.
    """
    import pymupdf as fitz
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except MemoryError:
        raise
    except Exception as e:  # noqa: BLE001
        raise UploadError(filename, f"not a valid PDF ({e})") from e
    if doc.page_count == 0:
        raise UploadError(filename, "PDF has no pages")
    if doc.page_count > remaining:
        raise UploadError(filename, f"too many pages; the limit is {max_pages} per script")
    return _render_pdf_pages(filename, doc)


def _render_pdf_pages(filename: str, doc) -> Iterator[Image.Image]:
    import pymupdf as fitz
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=150, colorspace=fitz.csRGB, alpha=False)
            yield Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except MemoryError:
        raise
    except Exception as e:  # noqa: BLE001
        raise UploadError(filename, f"not a valid PDF ({e})") from e


def _image_from_bytes(filename: str, data: bytes) -> Image.Image:
    _register_heif()
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        return img
    except Image.DecompressionBombError as e:
        raise UploadError(filename, "image is too large") from e
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise UploadError(filename, "not a readable image (use JPG, PNG or HEIC)") from e


def process_uploads(files: List[Tuple[str, bytes]], storage: PageStorage, max_pages: int = 60,
                    max_total_bytes: int = MAX_UPLOAD_BYTES) -> List[ProcessedPage]:
    total = sum(len(b) for _, b in files)
    if total > max_total_bytes:
        raise UploadError(files[0][0] if files else "upload", f"upload is {total // (1024 * 1024)} MB; the limit is {max_total_bytes // (1024 * 1024)} MB")
    pages: List[ProcessedPage] = []
    for filename, data in files:
        ext = Path(filename).suffix.lower()
        images: Iterable[Image.Image]
        if ext in PDF_EXTS:
            remaining = max_pages - len(pages)
            if remaining <= 0:
                raise UploadError(filename, f"too many pages; the limit is {max_pages} per script")
            images = _images_from_pdf(filename, data, remaining, max_pages)
        elif ext in IMAGE_EXTS:
            images = [_image_from_bytes(filename, data)]
        else:
            raise UploadError(filename, "unsupported file type (use PDF, JPG, PNG or HEIC)")
        # Normalise and store each page as it is produced so only one raw page is alive at a time.
        for img in images:
            if len(pages) >= max_pages:
                raise UploadError(filename, f"too many pages; the limit is {max_pages} per script")
            jpeg, w, h = _normalise(img)
            del img
            digest, rel = storage.put_jpeg(jpeg)
            pages.append(ProcessedPage(sha256=digest, storage_path=rel, width=w, height=h, source_filename=filename))
    return pages
