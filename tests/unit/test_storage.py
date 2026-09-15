import io
import threading

import pymupdf as fitz  # PyMuPDF
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


def test_put_jpeg_concurrent_identical_writes_are_safe(storage):
    data = _png(20, 20)
    results = []
    errors = []

    def worker():
        try:
            results.append(storage.put_jpeg(data))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 20
    digest, rel = results[0]
    assert all(r == (digest, rel) for r in results)
    assert list((storage.root / "pages").iterdir()) == [storage.abs(rel)]


def test_decompression_bomb_names_the_file(storage, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(UploadError) as e:
        process_uploads([("huge.png", _png(50, 50))], storage)
    assert e.value.filename == "huge.png"


def test_module_caps_image_pixels_at_50mp():
    import sms.storage  # noqa: F401 - importing sets the cap
    assert Image.MAX_IMAGE_PIXELS == 50_000_000


def test_pdf_pages_are_rendered_one_at_a_time(storage, monkeypatch):
    """Each page is normalised and stored before the next is rasterised (no whole-PDF list in memory)."""
    events = []
    real_get_pixmap = fitz.Page.get_pixmap

    def spy_get_pixmap(self, *a, **k):
        events.append("render")
        return real_get_pixmap(self, *a, **k)

    real_put = storage.put_jpeg

    def spy_put(data):
        events.append("store")
        return real_put(data)

    monkeypatch.setattr(fitz.Page, "get_pixmap", spy_get_pixmap)
    monkeypatch.setattr(storage, "put_jpeg", spy_put)
    pages = process_uploads([("scan.pdf", _pdf(3))], storage)
    assert len(pages) == 3
    assert events == ["render", "store"] * 3


def test_pdf_page_limit_checked_before_rendering(storage, monkeypatch):
    monkeypatch.setattr(fitz.Page, "get_pixmap", lambda *a, **k: pytest.fail("rendered a page past the limit"))
    with pytest.raises(UploadError) as e:
        process_uploads([("many.pdf", _pdf(3))], storage, max_pages=2)
    assert "limit is 2" in e.value.message
