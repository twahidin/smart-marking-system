import io

import fitz  # PyMuPDF
import pytest
from PIL import Image

from sms.storage import MAX_LONG_EDGE, PageStorage, UploadError, process_uploads


def _png(w, h, color="white"):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _pdf(pages):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((50, 100), f"page {i + 1}")
    return doc.tobytes()


@pytest.fixture
def storage(tmp_path):
    return PageStorage(tmp_path / "data")


def test_png_becomes_jpeg_and_is_content_addressed(storage):
    pages = process_uploads([("a.png", _png(100, 50))], storage)
    assert len(pages) == 1
    p = pages[0]
    assert p.storage_path == f"pages/{p.sha256}.jpg" and (p.width, p.height) == (100, 50)
    assert storage.read(p.storage_path)[:3] == b"\xff\xd8\xff"
    again = process_uploads([("b.png", _png(100, 50))], storage)
    assert again[0].sha256 == p.sha256


def test_pdf_splits_into_pages_in_order(storage):
    pages = process_uploads([("scan.pdf", _pdf(3))], storage)
    assert len(pages) == 3 and all(p.source_filename == "scan.pdf" for p in pages)
    assert len({p.sha256 for p in pages}) == 3


def test_files_ordered_then_pdf_pages(storage):
    pages = process_uploads([("1.png", _png(10, 10, "red")), ("2.pdf", _pdf(2)), ("3.png", _png(10, 10, "blue"))], storage)
    assert [p.source_filename for p in pages] == ["1.png", "2.pdf", "2.pdf", "3.png"]


def test_large_image_is_downscaled(storage):
    pages = process_uploads([("big.png", _png(4000, 2000))], storage)
    assert max(pages[0].width, pages[0].height) == MAX_LONG_EDGE


def test_bad_file_names_the_file(storage):
    with pytest.raises(UploadError) as e:
        process_uploads([("notes.txt", b"hello")], storage)
    assert e.value.filename == "notes.txt"


def test_corrupt_pdf_names_the_file(storage):
    with pytest.raises(UploadError) as e:
        process_uploads([("x.pdf", b"%PDF-1.4 garbage")], storage)
    assert e.value.filename == "x.pdf"


def test_page_limit(storage):
    with pytest.raises(UploadError):
        process_uploads([("many.pdf", _pdf(3))], storage, max_pages=2)


def test_total_size_limit(storage):
    with pytest.raises(UploadError):
        process_uploads([("a.png", _png(10, 10))], storage, max_total_bytes=10)
