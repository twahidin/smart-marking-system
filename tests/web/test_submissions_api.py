import asyncio
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest
from PIL import Image

from sms.schemas.marking import Rubric, RubricCriterion
from sms.web.errors import ApiError
from sms.web import uploads
from sms.web.routers import submissions as submissions_router
from sms.web.services.submissions import compute_totals, iso_utc

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2},
                              {"id": "c2", "description": "answer", "max_score": 3}]}


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def _bigger_png():
    buf = io.BytesIO()
    Image.new("RGB", (400, 400), "white").save(buf, format="PNG")
    return buf.getvalue()


def _create(auth, **over):
    data = {"label": "Tan Wei Ling", "subject": "math", "context": "Worksheet 3", "rubric": json.dumps(RUBRIC)}
    data.update(over)
    return auth.post("/api/submissions", data=data, files=[("files", ("p1.png", _png(), "image/png"))])


def test_requires_auth(client):
    assert client.get("/api/submissions").status_code == 401


def test_create_without_key_400(auth):
    r = _create(auth)
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key"


def _with_key(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    return auth


def test_create_returns_202_and_queues_job(auth):
    r = _create(_with_key(auth))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and len(body["pages"]) == 1
    lst = auth.get("/api/submissions").json()
    assert lst[0]["id"] == body["id"] and lst[0]["page_count"] == 1 and lst[0]["status"] == "queued"
    detail = auth.get(f"/api/submissions/{body['id']}").json()
    assert detail["job"]["status"] == "queued" and detail["marks"] == [] and detail["feedback"] is None


def test_create_bad_rubric_400(auth):
    r = _create(_with_key(auth), rubric="{}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_rubric"


def test_create_bad_file_names_it(auth):
    auth = _with_key(auth)
    r = auth.post("/api/submissions", data={"label": "x", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)},
                  files=[("files", ("notes.txt", b"hi", "text/plain"))])
    assert r.status_code == 400 and "notes.txt" in r.json()["error"]["message"]


def test_page_route_authenticated_and_serves_jpeg(auth, client):
    body = _create(_with_key(auth)).json()
    pid = body["pages"][0]["id"]
    r = auth.get(f"/api/pages/{pid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    client.cookies.clear()
    assert client.get(f"/api/pages/{pid}").status_code == 401


def test_retry_only_when_failed(auth, app):
    body = _create(_with_key(auth)).json()
    assert auth.post(f"/api/submissions/{body['id']}/retry").status_code == 409
    app.state.db.execute("UPDATE jobs SET status = 'failed'"); app.state.db.execute("UPDATE submissions SET status = 'failed'")
    assert auth.post(f"/api/submissions/{body['id']}/retry").status_code == 202
    assert auth.get(f"/api/submissions/{body['id']}").json()["status"] == "queued"


def test_detail_after_run_includes_marks_escalations_feedback(auth, app):
    body = _create(_with_key(auth)).json()
    sid = body["id"]
    db = app.state.db
    final = {"marks": [{"q_id": "q1", "criterion_scores": [2, 3], "total": 5, "confidence": 0.9, "rationale": "r", "evidence": "e"},
                       {"q_id": "q2", "criterion_scores": [1, 1], "total": 2, "confidence": 0.3, "rationale": "r2", "evidence": "e2"}]}
    feedback = {"summary": "s", "strengths": ["a"], "per_question_comments": [], "improvement_plan": [], "next_steps": []}
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, marks_json, final_marks_json, feedback_json, "
               "reviewed_json, submission_id, final_status) VALUES ('r1', 'complete', 'math', ?, ?, ?, ?, ?, ?, 'escalated')",
               (json.dumps(RUBRIC), json.dumps(final), json.dumps(final), json.dumps(feedback),
                json.dumps({"verdicts": [{"q_id": "q2", "verdict": "ESCALATE", "reviewer_note": "unsure"}], "final_marks": [], "disagreement_flags": []}), sid))
    db.execute("INSERT INTO teacher_queue (run_id, q_id, reason, status, submission_id) VALUES ('r1', 'q2', 'low marker confidence', 'pending', ?)", (sid,))
    db.execute("UPDATE submissions SET status = 'needs_you', run_id = 'r1' WHERE id = ?", (sid,))
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["status"] == "needs_you" and d["feedback"]["summary"] == "s"
    q2 = next(m for m in d["marks"] if m["q_id"] == "q2")
    assert q2["escalated"] and q2["reason"] == "low marker confidence" and q2["queue_id"] and q2["max"] == 5
    assert q2["reason_text"] == "Low confidence"
    assert d["totals"] == {"total": 7, "total_upper": 10, "total_max": 10}
    lst = auth.get("/api/submissions").json()[0]
    assert lst["total"] == 7 and lst["total_upper"] == 10 and lst["needs_you_qids"] == ["q2"]


def test_compute_totals_pure():
    rubric = Rubric(criterion_defs=[RubricCriterion(id="c1", description="d", max_score=2),
                                    RubricCriterion(id="c2", description="d", max_score=3)])
    final = [{"q_id": "q1", "total": 4}, {"q_id": "q2", "total": 1}]
    t = compute_totals(rubric, final, pending_qids={"q2"}, corrections={})
    assert t == {"total": 5, "total_upper": 9, "total_max": 10}
    t = compute_totals(rubric, final, pending_qids=set(), corrections={"q2": [2, 2]})
    assert t == {"total": 8, "total_upper": 8, "total_max": 10}


def test_page_route_missing_file_404(auth, app):
    body = _create(_with_key(auth)).json()
    pid = body["pages"][0]["id"]
    row = app.state.db.query("SELECT storage_path FROM pages WHERE id = :id", {"id": pid})[0]
    app.state.storage.abs(row["storage_path"]).unlink()
    r = auth.get(f"/api/pages/{pid}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_iso_utc_none():
    assert iso_utc(None) is None


def test_iso_utc_naive_datetime_assumed_utc():
    assert iso_utc(datetime(2026, 9, 15, 3, 4, 5)) == "2026-09-15T03:04:05Z"


def test_iso_utc_aware_datetime_converted_to_utc():
    tz = timezone.utc
    from datetime import timedelta
    plus8 = timezone(timedelta(hours=8))
    assert iso_utc(datetime(2026, 9, 15, 11, 4, 5, tzinfo=plus8)) == "2026-09-15T03:04:05Z"
    assert iso_utc(datetime(2026, 9, 15, 3, 4, 5, tzinfo=tz)) == "2026-09-15T03:04:05Z"


def test_iso_utc_sqlite_string():
    assert iso_utc("2026-09-15 03:04:05") == "2026-09-15T03:04:05Z"


def test_iso_utc_string_with_microseconds():
    assert iso_utc("2026-09-15 03:04:05.123456") == "2026-09-15T03:04:05Z"


def test_iso_utc_iso_t_string_with_offset_and_z():
    assert iso_utc("2026-09-15T11:04:05+08:00") == "2026-09-15T03:04:05Z"
    assert iso_utc("2026-09-15T03:04:05Z") == "2026-09-15T03:04:05Z"


def test_create_content_length_over_limit_413(auth):
    auth = _with_key(auth)
    over_limit = uploads.MAX_UPLOAD_BYTES + 1
    r = auth.post("/api/submissions",
                  data={"label": "x", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)},
                  files=[("files", ("p1.png", _png(), "image/png"))],
                  headers={"content-length": str(over_limit)})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_create_body_over_patched_limit_413(auth, monkeypatch):
    auth = _with_key(auth)
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 100)
    r = auth.post("/api/submissions",
                  data={"label": "x", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)},
                  files=[("files", ("p1.png", _bigger_png(), "image/png"))])
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


class _FakeUploadFile:
    """Mimics fastapi.UploadFile.read(n) by handing back pre-set chunks regardless of n,
    so _read_capped's chunk loop can be driven directly without going through HTTP."""

    def __init__(self, chunks):
        self._remaining = list(chunks) + [b""]
        self.calls = 0

    async def read(self, n):  # noqa: ARG002 - n unused, real UploadFile takes a size hint
        self.calls += 1
        return self._remaining.pop(0) if self._remaining else b""


def test_read_capped_raises_over_budget_without_reading_further_chunks():
    async def run():
        f = _FakeUploadFile([b"x" * 60, b"y" * 60, b"z" * 60])
        with pytest.raises(ApiError) as exc_info:
            await uploads._read_capped(f, budget=100)
        assert exc_info.value.status == 413 and exc_info.value.code == "too_large"
        # Only the first two chunks (60 + 60 = 120 > 100) should have been read; the
        # cap must trip before a third chunk is ever requested.
        assert f.calls == 2

    asyncio.run(run())


def test_read_capped_under_budget_returns_concatenated_bytes():
    async def run():
        f = _FakeUploadFile([b"a" * 30, b"b" * 30, b"c" * 30])
        data = await uploads._read_capped(f, budget=100)
        assert data == b"a" * 30 + b"b" * 30 + b"c" * 30
        # Three real chunks plus the terminating empty read.
        assert f.calls == 4

    asyncio.run(run())


def test_create_runs_upload_processing_off_the_event_loop(auth, monkeypatch):
    """CPU-bound create_submission must run in a worker thread, not on the event loop."""
    seen = {}
    real = submissions_router.create_submission

    def spy(*args, **kwargs):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return real(*args, **kwargs)

    monkeypatch.setattr(submissions_router, "create_submission", spy)
    r = _create(_with_key(auth))
    assert r.status_code == 202
    assert seen["on_loop"] is False


# --- version 2 (per-part) runs ---------------------------------------------------------------

from sms.web.services.submissions import compute_totals_v2  # noqa: E402
from tests.web.seed_v2 import RUBRIC as RUBRIC_BANDS, SCHEME, seed_v2  # noqa: E402


def test_detail_v2_parts_follow_the_scheme_and_totals_are_a_range_while_pending(auth, app):
    sid, qids = seed_v2(app)
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["marks_version"] == 2 and d["marks"] == [] and d["status"] == "needs_you"
    assert [p["q_id"] for p in d["parts"]] == ["1a", "1b", "2"]
    p1a, p1b, p2 = d["parts"]
    assert p1a["label"] == "1(a)" and p1a["question_text"] == "Solve 3x = 9"
    assert p1a["scheme"] == {"answer": "x = 3", "marks": [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""}
    assert p1a["extracted"] == "x = 3" and p1a["workings"] == "3x = 9, x = 9/3" and p1a["illegible"] is False
    assert [a["label"] for a in p1a["awarded"]] == ["M1", "A1"] and p1a["total"] == 2 and p1a["max"] == 2
    assert p1a["escalated"] is False and p1a["reason"] is None and p1a["queue_id"] is None and p1a["teacher"] is None
    assert p1a["reason_text"] is None
    assert p1a["in_scheme"] is True and p1a["confidence"] == 0.9 and p1a["justification"].startswith("M1 for")
    assert p1b["total"] == 0 and p1b["max"] == 1
    assert p2["escalated"] is True and p2["reason"] == "not in scheme" and p2["queue_id"] == qids["2"]
    assert p2["reason_text"] == "Answer not in the scheme — different method"
    assert p2["in_scheme"] is False and p2["max"] == 3
    # 1a 2/2 + 1b 0/1 settled; part 2 pending: marker's 1 in the lower bound, the row max (3) in the upper
    assert d["totals"] == {"total": 3, "total_upper": 5, "total_max": 6}
    lst = auth.get("/api/submissions").json()[0]
    assert lst["id"] == sid and lst["total"] == 3 and lst["total_upper"] == 5 and lst["total_max"] == 6
    assert lst["needs_you_qids"] == ["2"]


def test_detail_v2_rubric_parts_are_criteria_with_bands(auth, app):
    sid, qids = seed_v2(app, kind="rubric")
    d = auth.get(f"/api/submissions/{sid}").json()
    assert d["marks_version"] == 2 and [p["q_id"] for p in d["parts"]] == ["Content", "Language"]
    content, language = d["parts"]
    assert content["label"] == "Content" and content["scheme"]["bands"][0] == {"band": "A", "marks": 5, "descriptor": "Rich, relevant detail"}
    assert content["band"] == "A" and content["total"] == 5 and content["max"] == 5 and content["escalated"] is False
    assert content["extracted"]  # the whole response, since a rubric marks the response as one
    assert language["escalated"] and language["reason"] == "low confidence" and language["queue_id"] == qids["Language"]
    assert language["reason_text"] == "Low confidence"
    assert language["band"] == "B" and language["total"] == 2 and language["max"] == 5
    assert d["totals"] == {"total": 7, "total_upper": 10, "total_max": 10}


def test_compute_totals_v2_pure():
    parts = [{"q_id": "1a", "total": 2}, {"q_id": "1b", "total": 0}, {"q_id": "2", "total": 1}]
    t = compute_totals_v2("mark_scheme", SCHEME, parts, pending={"2"}, corrections={})
    assert t == {"total": 3, "total_upper": 5, "total_max": 6}
    # a teacher's resolution pins the part to the teacher's total on both bounds
    t = compute_totals_v2("mark_scheme", SCHEME, parts, pending=set(),
                          corrections={"2": {"version": 2, "allocations": [], "total": 2}})
    assert t == {"total": 4, "total_upper": 4, "total_max": 6}
    # a part the marker never returned counts 0 (not pending) and still contributes to the max
    t = compute_totals_v2("mark_scheme", SCHEME, parts[:2], pending=set(), corrections={})
    assert t == {"total": 2, "total_upper": 2, "total_max": 6}
    marks = [{"criterion": "Content", "marks": 5}, {"criterion": "Language", "marks": 2}]
    t = compute_totals_v2("rubric", RUBRIC_BANDS, marks, pending={"Language"}, corrections={})
    assert t == {"total": 7, "total_upper": 10, "total_max": 10}
    t = compute_totals_v2("rubric", RUBRIC_BANDS, marks, pending=set(), corrections={"Language": {"version": 2, "band": "A", "marks": 5}})
    assert t == {"total": 10, "total_upper": 10, "total_max": 10}


def test_create_rejects_a_typed_assignment_with_no_scheme(auth, app):
    """A mark-scheme / rubric assignment whose scheme is still empty cannot be marked against: 400 no_scheme."""
    _with_key(auth)
    for kind in ("mark_scheme", "rubric"):
        t = auth.post("/api/assignments", json={"title": f"Empty {kind}", "subject": "math", "context": "", "rubric": RUBRIC,
                                               "scheme_kind": kind, "questions": [{"q_id": "1", "text": "Q", "max_marks": 2}]}).json()
        r = _create(auth, assignment_id=str(t["id"]))
        assert r.status_code == 400 and r.json()["error"]["code"] == "no_scheme", kind
    # a criteria assignment has no per-question scheme and uploads as before
    t = auth.post("/api/assignments", json={"title": "Quick", "subject": "math", "context": "", "rubric": RUBRIC, "scheme_kind": "criteria"}).json()
    assert _create(auth, assignment_id=str(t["id"])).status_code == 202


def test_create_stores_the_scheme_kind_the_script_was_uploaded_against(auth, app):
    _with_key(auth)
    t = auth.post("/api/assignments", json={"title": "Essay", "subject": "language", "context": "", "rubric": RUBRIC, "scheme_kind": "rubric",
                                           "scheme": [{"criterion": "Content", "bands": [{"band": "A", "marks": 5, "descriptor": ""}]}]}).json()
    typed = _create(auth, assignment_id=str(t["id"])).json()["id"]
    quick = _create(auth).json()["id"]
    kinds = {r["id"]: r["scheme_kind"] for r in app.state.db.query("SELECT id, scheme_kind FROM submissions")}
    assert kinds == {typed: "rubric", quick: "criteria"}


def test_detail_matches_extraction_q_ids_loosely(auth, app):
    """The extractor may write "Q1(a)" where the scheme says "1a": the student's answer still lands on the row."""
    extracted = {"questions": [
        {"q_id": "Q1(a)", "transcribed_answer": "x = 3", "workings": "3x = 9", "confidence": 0.9, "needs_human_transcription": False},
        {"q_id": "1 (b)", "transcribed_answer": "6", "workings": "", "confidence": 0.8, "needs_human_transcription": True},
        {"q_id": "Q2", "transcribed_answer": "x^2 + 2x + 1", "workings": "", "confidence": 0.9, "needs_human_transcription": False},
    ]}
    sid, qids = seed_v2(app, extracted=extracted)
    d = auth.get(f"/api/submissions/{sid}").json()
    p1a, p1b, p2 = d["parts"]
    assert p1a["extracted"] == "x = 3" and p1a["workings"] == "3x = 9" and p1a["illegible"] is False
    assert p1b["extracted"] == "6" and p1b["illegible"] is True
    assert p2["extracted"] == "x^2 + 2x + 1"
    it = auth.get("/api/queue").json()[0]
    assert it["q_id"] == "2" and it["transcription"] == "x^2 + 2x + 1"


# --- file submissions (.py / .sb3 / .xlsx, zips, mixed uploads) --------------------------------
from tests.web.seed_v2 import QUESTIONS  # noqa: E402


def _tpl_v2(auth):
    """A mark-scheme assignment with a scheme: files can only be marked against one of these."""
    _with_key(auth)
    return auth.post("/api/assignments", json={"title": "Program 1", "subject": "math", "context": "",
                                               "rubric": RUBRIC, "scheme_kind": "mark_scheme",
                                               "questions": QUESTIONS, "scheme": SCHEME}).json()["id"]


def _data(tid=None, **over):
    data = {"label": "S", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)}
    if tid is not None:
        data["assignment_id"] = str(tid)
    data.update(over)
    return data


def test_upload_python_file_creates_files_submission(auth):
    tid = _tpl_v2(auth)
    r = auth.post("/api/submissions", data=_data(tid, label="S1"),
                  files=[("files", ("prog.py", b"print(1)\n", "text/x-python"))])
    assert r.status_code == 202
    d = auth.get(f"/api/submissions/{r.json()['id']}").json()
    assert d["input_kind"] == "files" and d["pages"] == [] and [f["name"] for f in d["files"]] == ["prog.py"]
    assert d["files"][0]["kind"] == "py" and d["files"][0]["size"] == 9 and d["files"][0]["text_rendered"] is None
    assert d["files"][0]["deleted"] is False and d["files"][0]["matched"] is False


def test_a_file_cited_only_in_workings_still_counts_as_used(auth, app):
    """The segmenter puts supporting sources — a helper module, the cells a formula depends on — in
    `workings`, so both halves of a part decide whether a file was read."""
    extracted = {"questions": [{"q_id": "1a", "transcribed_answer": "[prog.py L1-2] print(1)",
                                "workings": "[utils.py L4-9] def helper(): return 1",
                                "confidence": 0.9, "needs_human_transcription": False}]}
    sid, _ = seed_v2(app, extracted=extracted, queue={})
    for name in ("prog.py", "utils.py", "spare.py"):
        app.state.db.execute("INSERT INTO submission_files (submission_id, name, kind, size, sha256, stored_path) "
                             "VALUES (:s, :n, 'py', 1, :h, :p)",
                             {"s": sid, "n": name, "h": f"h-{name}", "p": f"files/aa/{name}"})
    d = auth.get(f"/api/submissions/{sid}").json()
    assert {f["name"]: f["matched"] for f in d["files"]} == {"prog.py": True, "utils.py": True, "spare.py": False}


def test_mixed_upload(auth):
    tid = _tpl_v2(auth)
    r = auth.post("/api/submissions", data=_data(tid, label="S2"),
                  files=[("files", ("p.png", _png(), "image/png")),
                         ("files", ("s.xlsx", b"PK\x03\x04", "application/octet-stream"))])
    assert r.status_code == 202
    d = auth.get(f"/api/submissions/{r.json()['id']}").json()
    assert d["input_kind"] == "mixed" and len(d["pages"]) == 1 and len(d["files"]) == 1


def test_files_need_a_scheme_assignment(auth):
    _with_key(auth)
    r = auth.post("/api/submissions", data=_data(label="S3"),
                  files=[("files", ("prog.py", b"x=1", "text/x-python"))])
    assert r.status_code == 400 and r.json()["error"]["code"] == "files_need_scheme"


def test_bad_file_named(auth):
    tid = _tpl_v2(auth)
    r = auth.post("/api/submissions", data=_data(tid, label="S4"),
                  files=[("files", ("virus.exe", b"x", "application/octet-stream"))])
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_file" and "virus.exe" in r.json()["error"]["message"]


def test_zip_is_expanded_and_ignored_entries_are_reported(auth):
    tid = _tpl_v2(auth)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("prog.py", b"x=1")
        z.writestr("notes.txt", b"hi")
        z.writestr("__MACOSX/._prog.py", b"junk")
    r = auth.post("/api/submissions", data=_data(tid, label="S5"),
                  files=[("files", ("work.zip", buf.getvalue(), "application/zip"))])
    assert r.status_code == 202 and r.json()["ignored"] == ["notes.txt"] and r.json()["files"] == ["prog.py"]
    d = auth.get(f"/api/submissions/{r.json()['id']}").json()
    assert d["input_kind"] == "files" and [f["name"] for f in d["files"]] == ["prog.py"]


def test_pages_only_upload_keeps_input_kind_pages(auth):
    r = _create(_with_key(auth))
    d = auth.get(f"/api/submissions/{r.json()['id']}").json()
    assert d["input_kind"] == "pages" and d["files"] == []


def test_list_counts_files_beside_pages(auth):
    """The Submissions table shows "N files" for a script with no pages, so the list carries the count."""
    tid = _tpl_v2(auth)
    files = auth.post("/api/submissions", data=_data(tid, label="Files only"),
                      files=[("files", ("prog.py", b"print(1)\n", "text/x-python")),
                             ("files", ("utils.py", b"x = 1\n", "text/x-python"))]).json()["id"]
    pages = _create(auth, label="Pages only").json()["id"]
    rows = {r["id"]: r for r in auth.get("/api/submissions").json()}
    assert rows[files]["file_count"] == 2 and rows[files]["page_count"] == 0
    assert rows[pages]["file_count"] == 0 and rows[pages]["page_count"] == 1


def test_file_bytes_are_stored_content_addressed(auth, app):
    tid = _tpl_v2(auth)
    r = auth.post("/api/submissions", data=_data(tid, label="S6"),
                  files=[("files", ("prog.py", b"print(1)\n", "text/x-python"))])
    row = app.state.db.query("SELECT * FROM submission_files WHERE submission_id = :s", {"s": r.json()["id"]})[0]
    digest = hashlib.sha256(b"print(1)\n").hexdigest()
    assert row["sha256"] == digest and row["stored_path"] == f"files/{digest[:2]}/{digest}.py"
    assert app.state.storage.abs(row["stored_path"]).read_bytes() == b"print(1)\n"


def test_unreadable_zip_entries_are_400_bad_file_naming_the_zip(auth):
    """A password-protected or damaged archive must be a named 400, never a 500."""
    from tests.unit.test_files_intake import _zip_damaged_stream, _zip_unreadable_method
    tid = _tpl_v2(auth)
    for data in (_zip_unreadable_method(), _zip_damaged_stream()):
        r = auth.post("/api/submissions", data=_data(tid, label="S7"),
                      files=[("files", ("work.zip", data, "application/zip"))])
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "bad_file" and "work.zip" in r.json()["error"]["message"]


def test_no_files_at_all_is_rejected(auth, app):
    from sms.web.services.submissions import create_submission
    with pytest.raises(ApiError) as e:
        create_submission(app.state.db, app.state.storage, app.state.jobs, label="x", subject="math",
                          context="", rubric_json=json.dumps(RUBRIC), files=[])
    assert e.value.code == "no_files" and e.value.message == "Add at least one page or file"
