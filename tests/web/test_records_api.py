import io
import json
import zipfile

from docx import Document
from openpyxl import load_workbook

from tests.web.seed_v2 import seed_v2

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_record_requires_auth(client):
    assert client.get("/api/submissions/1/record.docx").status_code == 401
    assert client.post("/api/submissions/records.zip", json={"ids": [1]}).status_code == 401


def test_record_docx_downloads_the_marking_record(auth, app):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x", "rpm_limit": 60,
                                    "confidence_threshold": 0})
    tid = auth.post("/api/assignments", json={"title": "Sec 4 Quadratics", "subject": "math", "context": "",
                                              "rubric": {"criterion_defs": [{"id": "c1", "description": "d", "max_score": 1}]},
                                              "scheme_kind": "mark_scheme"}).json()["id"]
    sid, _ = seed_v2(app, label="Tan Wei Ling", assignment_id=tid)
    r = auth.get(f"/api/submissions/{sid}/record.docx")
    assert r.status_code == 200 and r.headers["content-type"].startswith(DOCX)
    assert r.headers["content-disposition"] == ('attachment; filename="tan-wei-ling-marking-record.docx"; '
                                                "filename*=UTF-8''Tan%20Wei%20Ling-marking-record.docx")
    text0 = "\n".join(p.text for p in Document(io.BytesIO(r.content)).paragraphs)
    run_created = app.state.db.query("SELECT created_at FROM marking_runs WHERE submission_id = :s", {"s": sid})[0]["created_at"]
    from sms.timeutil import iso_utc
    assert iso_utc(run_created)[:10] in text0
    doc = Document(io.BytesIO(r.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Sec 4 Quadratics" in text and "Tan Wei Ling" in text and "gpt-5-mini" in text
    table = doc.tables[0]
    assert [table.rows[i].cells[0].text for i in (1, 2, 3)] == ["1(a)", "1(b)", "2"]
    assert table.rows[3].cells[4].text == "Teacher to review"
    assert table.rows[1].cells[4].text == "2 / 2" and table.rows[1].cells[1].text == "x = 3  [M1 A1]"
    # a label with no ASCII letters falls back to script-<id> for the ASCII filename; filename* keeps the original
    sid_u, _ = seed_v2(app, label="陈伟", run_id="ru")
    r = auth.get(f"/api/submissions/{sid_u}/record.docx")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == (f'attachment; filename="script-{sid_u}-marking-record.docx"; '
                                                "filename*=UTF-8''%E9%99%88%E4%BC%9F-marking-record.docx")


def test_record_404_and_409_not_marked(auth, app):
    assert auth.get("/api/submissions/999/record.docx").status_code == 404
    sid = app.state.db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) "
                              "VALUES ('New', 'math', '', '{\"criterion_defs\": []}', 'queued') RETURNING id")
    r = auth.get(f"/api/submissions/{sid}/record.docx")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_marked"
    r = auth.post("/api/submissions/records.zip", json={"ids": [sid]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_marked"
    r = auth.post("/api/submissions/records.zip", json={"ids": [999]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert auth.post("/api/submissions/records.zip", json={"ids": []}).status_code == 400


def test_records_zip_bundles_docx_per_student_and_markbook(auth, app):
    a, _ = seed_v2(app, label="Tan", run_id="ra")
    b, _ = seed_v2(app, label="Lim", run_id="rb", queue={})
    r = auth.post("/api/submissions/records.zip", json={"ids": [a, b]})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == 'attachment; filename="marking-records.zip"'
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.namelist() == ["tan-marking-record.docx", "lim-marking-record.docx", "markbook.xlsx"]
        wb = load_workbook(io.BytesIO(z.read("markbook.xlsx")))
        assert wb.sheetnames == ["Quick mark", "Rows"]  # no assignment on either script
        rows = [[c.value for c in row] for row in wb["Quick mark"].iter_rows()]
        assert rows[0] == ["Student", "1(a)", "1(b)", "2", "Total", "Max"]
        assert rows[1] == ["Tan", 2, 0, "Review", "3–5", 6]
        assert rows[2] == ["Lim", 2, 0, 1, 3, 6]
        assert wb["Rows"].max_row == 1 + 6


def test_records_zip_markbook_has_a_sheet_per_assignment(auth, app):
    db = app.state.db
    ta = db.insert("INSERT INTO assignment_templates (title, subject, rubric_json, scheme_kind) VALUES ('Quadratics', 'math', '{\"criterion_defs\": []}', 'mark_scheme') RETURNING id")
    tb = db.insert("INSERT INTO assignment_templates (title, subject, rubric_json, scheme_kind) VALUES ('Essay', 'language', '{\"criterion_defs\": []}', 'rubric') RETURNING id")
    a, _ = seed_v2(app, label="Tan", run_id="ra", queue={}, assignment_id=ta)
    b, _ = seed_v2(app, label="Lim", run_id="rb", kind="rubric", queue={}, assignment_id=tb, subject="language")
    r = auth.post("/api/submissions/records.zip", json={"ids": [a, b]})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        wb = load_workbook(io.BytesIO(z.read("markbook.xlsx")))
        assert wb.sheetnames == ["Quadratics", "Essay", "Rows"]
        assert [c.value for c in wb["Quadratics"][1]] == ["Student", "1(a)", "1(b)", "2", "Total", "Max"]
        assert [c.value for c in wb["Essay"][1]] == ["Student", "Content", "Language", "Total", "Max"]
        assert [c.value for c in wb["Essay"][2]] == ["Lim", 5, 2, 7, 10]
        rows = [[c.value for c in row] for row in wb["Rows"].iter_rows()]
        assert rows[0][:2] == ["Student", "Assignment"] and {r[1] for r in rows[1:]} == {"Quadratics", "Essay"}


def test_v1_record_still_renders(auth, app):
    db = app.state.db
    rubric = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}, {"id": "c2", "description": "answer", "max_score": 3}]}
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, run_id) "
                    "VALUES ('Old', 'math', 'Worksheet 3', :r, 'done', 'r1') RETURNING id", {"r": json.dumps(rubric)})
    final = {"marks": [{"q_id": "q1", "criterion_scores": [2, 3], "total": 5, "confidence": 0.9, "rationale": "r", "evidence": "e"}]}
    db.execute("INSERT INTO marking_runs (run_id, stage, subject, rubric_json, marks_json, final_marks_json, submission_id, final_status) "
               "VALUES ('r1', 'complete', 'math', :rub, :m, :m, :s, 'complete')", {"rub": json.dumps(rubric), "m": json.dumps(final), "s": sid})
    r = auth.get(f"/api/submissions/{sid}/record.docx")
    assert r.status_code == 200
    table = Document(io.BytesIO(r.content)).tables[0]
    assert table.rows[1].cells[0].text == "Q1" and table.rows[1].cells[4].text == "5 / 5"
    assert table.rows[1].cells[1].text == "c1 method (2) · c2 answer (3)"
