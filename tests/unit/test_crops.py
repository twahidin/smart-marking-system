"""Answer crops: the region of a page a marked part came from, kept after the page is deleted."""
import io

from PIL import Image

from sms.schemas.extraction import ExtractedQuestion, ExtractedScript
from sms.storage import PageStorage
from sms.web.services.crops import PAD, crop_box, crop_parts


def _page(w=1000, h=1400):
    im = Image.new("RGB", (w, h), "white")
    buf = io.BytesIO(); im.save(buf, "JPEG"); return buf.getvalue()


def test_crop_box_pads_and_snaps_to_the_page():
    assert crop_box(1000, 1400, [0.10, 0.20, 0.50, 0.40]) == (68, 252, 532, 588)   # 8% of the box each side (min 2% of the page)
    assert crop_box(1000, 1400, [0.0, 0.0, 0.3, 0.1]) == (0, 0, 324, 168)          # never outside the page; thin box gets the 2% minimum
    assert crop_box(1000, 1400, [0.7, 0.9, 1.0, 1.0]) == (676, 1232, 1000, 1400)


def test_crop_box_rejects_tiny_or_inverted_boxes():
    assert crop_box(1000, 1400, [0.5, 0.5, 0.51, 0.505]) is None      # under 1% of the page
    assert crop_box(1000, 1400, [0.6, 0.6, 0.4, 0.8]) is None         # x1 < x0
    assert crop_box(1000, 1400, None) is None


def test_crop_parts_stores_a_crop_per_located_part_and_whole_page_otherwise(tmp_path):
    storage = PageStorage(tmp_path)
    pages = [_page(), _page(800, 600)]
    ex = ExtractedScript(questions=[
        ExtractedQuestion(q_id="1a", transcribed_answer="x=3", confidence=0.9, page=0, box=[0.1, 0.1, 0.6, 0.3]),
        ExtractedQuestion(q_id="1b", transcribed_answer="9", confidence=0.9, page=1, box=None),        # no box → whole page
        ExtractedQuestion(q_id="2", transcribed_answer="", confidence=0.2, page=7, box=[0.1, 0.1, 0.5, 0.5]),  # bad page → skipped
        ExtractedQuestion(q_id="3", transcribed_answer="…", confidence=0.9, page=None, box=None),      # unlocated → skipped
    ])
    crops = crop_parts(storage, pages, ex)
    assert [c.q_id for c in crops] == ["1a", "1b"]
    a, b = crops
    assert a.page_index == 0 and not a.whole_page and a.box == [0.1, 0.1, 0.6, 0.3]
    assert (a.width, a.height) == (580, 336)
    assert b.page_index == 1 and b.whole_page and b.box is None and (b.width, b.height) == (800, 600)
    for c in crops:
        assert storage.abs(c.storage_path).exists() and c.storage_path.startswith("crops/")
        assert Image.open(storage.abs(c.storage_path)).size == (c.width, c.height)
