"""One combined PDF of a class's scripts: split at each cover, read the covers, hand in per student."""
import io
import json

import pymupdf as fitz
import pytest
from PIL import Image

from sms.web.errors import ApiError
from sms.web.services import bulk_pdf
from sms.web.services.bulk_pdf import Booklet, CoverInfo, booklet_pages, find_booklets, match_student, open_pdf
from tests.web.test_class_assignments_api import _bulk_setup, _with_key

A3 = fitz.paper_rect("a3-l")   # a scanned two-page spread
HALF = A3.width / 2


def _cover(page, x0, name, index):
    page.draw_rect(fitz.Rect(x0 + 60, 140, x0 + 160, 230), color=(0, 0, 0), width=2)
    page.insert_text((x0 + 85, 200), "G3", fontsize=40)
    page.insert_text((x0 + 60, 100), f"Name: {name}      Index Number: {index}      Class: 3/4", fontsize=12)
    for k, line in enumerate(["Riverside Secondary School", "End-of-Year Examination 2026", "Secondary 3"]):
        page.insert_text((x0 + 220, 160 + 22 * k), line, fontsize=16)
    page.insert_text((x0 + 60, 300), "Computing Paper 1", fontsize=18)
    page.draw_rect(fitz.Rect(x0 + 380, 700, x0 + 560, 790), color=(0, 0, 0), width=1.5)


def _content(page, x0, seed):
    for k in range(28):
        page.insert_text((x0 + 50, 70 + 26 * k), f"{seed}.{k} Answer every part of the question shown here ........ [{k % 4 + 1}]", fontsize=10)


def _combined(students=(("Amirah", "3401"), ("Ben", "3402"), ("Chloe", "3405")), extra_last=1):
    """Each booklet: [blank back | cover], [BLANK PAGE | content], two content spreads; the last has `extra_last` more."""
    doc = fitz.open()
    for n, (name, index) in enumerate(students):
        p = doc.new_page(width=A3.width, height=A3.height)
        _cover(p, HALF, name, index)
        p = doc.new_page(width=A3.width, height=A3.height)
        p.insert_text((150, 420), "BLANK PAGE", fontsize=14)
        _content(p, HALF, n * 10)
        spreads = 2 + (extra_last if n == len(students) - 1 else 0)
        for k in range(spreads):
            p = doc.new_page(width=A3.width, height=A3.height)
            _content(p, 0, n * 10 + k + 1)
            _content(p, HALF, n * 10 + k + 5)
    return doc.tobytes()


def test_splits_at_every_cover_whatever_each_booklet_s_length():
    doc = open_pdf(_combined())
    assert [(b.start, b.end, b.cover_half) for b in find_booklets(doc)] == [(1, 4, 1), (5, 8, 1), (9, 13, 1)]


def test_a_booklet_becomes_single_pages_without_the_blank_ones():
    doc = open_pdf(_combined())
    files = booklet_pages(doc, Booklet(start=1, end=4, cover_half=1))
    # back cover and "BLANK PAGE" dropped: cover, one content half, then two full spreads
    assert [n for n, _ in files] == ["p001b.jpg", "p002b.jpg", "p003a.jpg", "p003b.jpg", "p004a.jpg", "p004b.jpg"]
    w, h = Image.open(io.BytesIO(files[2][1])).size
    assert h > w and 1900 <= max(w, h) <= 2000


def test_rejects_a_file_that_is_not_a_pdf():
    with pytest.raises(ApiError) as e:
        open_pdf(b"not a pdf")
    assert e.value.code == "bad_file"


STUDENTS = [{"id": 11, "reg_no": 3401, "name": "Amirah"}, {"id": 12, "reg_no": 3402, "name": "Ben Lim Jun Wei"},
            {"id": 13, "reg_no": 3405, "name": "Chloe Tan"}]


@pytest.mark.parametrize("info, expected", [
    (CoverInfo(index_number="3402", name=None), (12, "index")),
    (CoverInfo(index_number=" 34 05 ", name="??"), (13, "index")),
    (CoverInfo(index_number=None, name="ben"), (12, "name")),
    (CoverInfo(index_number="9999", name="Chloe Tan"), (13, "name")),
    (CoverInfo(index_number=None, name="Tan"), (13, "name")),
    (CoverInfo(index_number=None, name=None), (None, None)),
])
def test_matches_a_cover_by_index_number_then_by_name(info, expected):
    assert match_student(info, STUDENTS) == expected


def test_an_index_like_3407_matches_register_7_when_the_class_is_numbered_1_to_40():
    small = [{"id": 1, "reg_no": 7, "name": "Amirah"}, {"id": 2, "reg_no": 12, "name": "Ben"}]
    assert match_student(CoverInfo(index_number="3407", name=None), small) == (1, "index")
    assert match_student(CoverInfo(index_number="3401", name=None), small) == (None, None)


# --- the routes ------------------------------------------------------------------------------------

def _class(auth):
    _with_key(auth)
    c, ca = _bulk_setup(auth, rows=({"reg_no": 3401, "name": "Amirah"}, {"reg_no": 3402, "name": "Ben Lim Jun Wei"},
                                    {"reg_no": 3405, "name": "Chloe Tan"}))
    students = {s["reg_no"]: s for s in auth.get(f"/api/classes/{c['id']}/students").json()}
    return f"/api/classes/{c['id']}/assignments/{ca['id']}", students


def _fake_reader(monkeypatch, infos):
    seen = []
    monkeypatch.setattr(bulk_pdf, "COVER_READERS", 1)   # read in order, so the fake answers line up

    def factory(settings):
        def read(png):
            assert png.startswith(b"\xff\xd8")   # a JPEG
            seen.append(png)
            return infos[len(seen) - 1]
        return read
    monkeypatch.setattr(bulk_pdf, "model_cover_reader", factory)
    return seen


def _pdf_file(data):
    return [("pdf", ("scripts.pdf", data, "application/pdf"))]


def test_preview_proposes_a_student_per_booklet_from_its_cover(auth, monkeypatch):
    base, students = _class(auth)
    seen = _fake_reader(monkeypatch, [CoverInfo(index_number="3401", name="Amirah"), CoverInfo(index_number=None, name=None),
                                      CoverInfo(index_number=None, name="chloe")])
    r = auth.post(f"{base}/bulk/pdf/preview", files=_pdf_file(_combined()))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(seen) == 3 and body["pdf_pages"] == 13
    rows = [(b["start"], b["end"], b["student_id"], b["matched_by"]) for b in body["booklets"]]
    assert rows == [(1, 4, students[3401]["id"], "index"), (5, 8, None, None), (9, 13, students[3405]["id"], "name")]
    assert body["booklets"][0]["cover"].startswith("data:image/jpeg;base64,")
    assert body["booklets"][1]["read"] == {"index_number": None, "name": None}
    assert {s["reg_no"] for s in body["students"]} == {3401, 3402, 3405}
    assert body["read_error"] is None


def test_preview_says_why_when_no_cover_could_be_read(auth, monkeypatch):
    base, _ = _class(auth)

    def factory(settings):
        def read(jpg):
            raise RuntimeError("Error code: 400 - A is not a valid model ID")
        return read
    monkeypatch.setattr(bulk_pdf, "model_cover_reader", factory)
    body = auth.post(f"{base}/bulk/pdf/preview", files=_pdf_file(_combined())).json()
    assert [b["student_id"] for b in body["booklets"]] == [None, None, None]
    assert "A is not a valid model ID" in body["read_error"]


def test_preview_and_commit_need_an_api_key(auth):
    c, ca = _bulk_setup(auth)
    base = f"/api/classes/{c['id']}/assignments/{ca['id']}"
    assert auth.post(f"{base}/bulk/pdf/preview", files=_pdf_file(_combined())).json()["error"]["code"] == "no_key"
    r = auth.post(f"{base}/bulk/pdf", data={"booklets": "[]"}, files=_pdf_file(_combined()))
    assert r.json()["error"]["code"] == "no_key"


def test_commit_hands_in_each_confirmed_booklet_and_skips_or_replaces_existing_ones(auth, app):
    base, students = _class(auth)
    pdf = _combined()
    chosen = [{"start": 1, "end": 4, "student_id": students[3401]["id"]}, {"start": 9, "end": 13, "student_id": students[3405]["id"]}]
    r = auth.post(f"{base}/bulk/pdf", data={"booklets": json.dumps(chosen)}, files=_pdf_file(pdf))
    assert r.status_code == 202, r.text
    body = r.json()
    assert [(c["reg_no"], c["pages"]) for c in body["created"]] == [(3401, 6), (3405, 8)] and body["failed"] == []
    pages = app.state.db.query("SELECT COUNT(*) AS n FROM pages p JOIN submissions s ON s.id = p.submission_id "
                               "WHERE s.student_id = :s", {"s": students[3405]["id"]})[0]["n"]
    assert pages == 8

    again = auth.post(f"{base}/bulk/pdf", data={"booklets": json.dumps(chosen[:1])}, files=_pdf_file(pdf)).json()
    assert again["created"] == [] and again["skipped"] == [{"reg_no": 3401}]
    replaced = auth.post(f"{base}/bulk/pdf?replace=1", data={"booklets": json.dumps(chosen[:1])}, files=_pdf_file(pdf)).json()
    assert [c["reg_no"] for c in replaced["created"]] == [3401]


@pytest.mark.parametrize("chosen, message", [
    ([{"start": 1, "end": 4, "student_id": "S"}, {"start": 5, "end": 8, "student_id": "S"}], "matched to two booklets"),
    ([{"start": 12, "end": 14, "student_id": "S"}], "outside this 13-page PDF"),
    ([{"start": 1, "end": 4, "student_id": 999999}], "isn't in this class"),
    ([{"start": 1}], "needs a start page"),
])
def test_commit_refuses_a_bad_set_of_booklets_before_handing_anything_in(auth, app, chosen, message):
    base, students = _class(auth)
    for c in chosen:
        if c.get("student_id") == "S":
            c["student_id"] = students[3401]["id"]
    r = auth.post(f"{base}/bulk/pdf", data={"booklets": json.dumps(chosen)}, files=_pdf_file(_combined()))
    assert r.status_code == 400 and message in r.json()["error"]["message"]
    assert app.state.db.query("SELECT COUNT(*) AS n FROM submissions")[0]["n"] == 0
