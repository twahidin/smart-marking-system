import io
import zipfile

from openpyxl import load_workbook

from sms.records.builder import Record, RecordRow
from sms.records.bundle import bundle_zip, record_filename
from sms.records.xlsx import render_xlsx


def _row(label, awarded, marks, mx=2, to_review=False):
    return RecordRow(key=label, label=label, scheme_answer="ans", student_answer="x", justification="j", awarded=awarded,
                     teacher="", to_review=to_review, awarded_marks=marks, max_marks=mx)


def _record(student, sid, rows, total, upper, mx, review=0, title="Sec 4 Quadratics", assignment_id=3, **over):
    fields = dict(title=title, student=student, marked_at="2026-09-15T03:06:07Z", model="m", rows=rows,
                  total_awarded=total, total_upper=upper, total_max=mx, to_review_count=review, rubric_page=None,
                  submission_id=sid, kind="mark_scheme", assignment_id=assignment_id)
    fields.update(over)
    return Record(**fields)


REC_A = _record("Tan Wei Ling", 1, [_row("1(a)", "2 / 2", 2), _row("1(b)", "Teacher to review", None, to_review=True)], 2, 4, 4, 1)
REC_B = _record("Lim", 2, [_row("1(a)", "1 / 2", 1), _row("1(b)", "2 / 2 (teacher)", 2), _row("2", "3 / 3", 3, 3)], 6, 6, 7)


def test_markbook_and_rows_sheets():
    data = render_xlsx([REC_A, REC_B])
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Sec 4 Quadratics", "Rows"]
    mb = wb["Sec 4 Quadratics"]
    rows = [[c.value for c in r] for r in mb.iter_rows()]
    assert rows[0] == ["Student", "1(a)", "1(b)", "2", "Total", "Max"]
    assert rows[1] == ["Tan Wei Ling", 2, "Review", None, "2–4", 4]
    assert rows[2] == ["Lim", 1, 2, 3, 6, 7]
    rs = wb["Rows"]
    rows = [[c.value for c in r] for r in rs.iter_rows()]
    assert rows[0] == ["Student", "Assignment", "Question & part", "Marking scheme answer", "Student's answer (extracted)",
                       "Justification", "Awarded mark", "Teacher's mark"]
    assert len(rows) == 1 + 2 + 3
    assert rows[2] == ["Tan Wei Ling", "Sec 4 Quadratics", "1(b)", "ans", "x", "j", "Teacher to review", None]
    assert rows[4] == ["Lim", "Sec 4 Quadratics", "1(b)", "ans", "x", "j", "2 / 2 (teacher)", None]


def test_markbook_has_one_sheet_per_assignment_with_its_own_columns():
    """Records of different assignments never share a markbook: each assignment gets a sheet named after it
    (a quick mark with no assignment is "Quick mark"), with only its own parts as columns."""
    essay = _record("Ng", 3, [_row("Content", "5 / 5", 5, 5), _row("Language", "3 / 5", 3, 5)], 8, 8, 10,
                    title="Narrative essay: [draft] * 2026/27 — a title long enough to be cut", assignment_id=4, kind="rubric")
    quick = _record("Ong", 4, [_row("Q1", "2 / 2", 2)], 2, 2, 2, title="Worksheet", assignment_id=None, kind="criteria")
    same_title = _record("Teo", 5, [_row("1(a)", "1 / 2", 1)], 1, 1, 2, title="Sec 4 Quadratics", assignment_id=9)
    wb = load_workbook(io.BytesIO(render_xlsx([REC_A, essay, REC_B, quick, same_title])))
    assert wb.sheetnames == ["Sec 4 Quadratics", "Narrative essay draft 2026 27 —", "Quick mark", "Sec 4 Quadratics (2)", "Rows"]
    assert all(len(n) <= 31 for n in wb.sheetnames)
    sheet = lambda n: [[c.value for c in r] for r in wb[n].iter_rows()]  # noqa: E731
    assert sheet("Sec 4 Quadratics")[0] == ["Student", "1(a)", "1(b)", "2", "Total", "Max"]
    assert [r[0] for r in sheet("Sec 4 Quadratics")[1:]] == ["Tan Wei Ling", "Lim"]
    assert sheet("Narrative essay draft 2026 27 —") == [["Student", "Content", "Language", "Total", "Max"], ["Ng", 5, 3, 8, 10]]
    assert sheet("Quick mark") == [["Student", "Q1", "Total", "Max"], ["Ong", 2, 2, 2]]
    assert sheet("Sec 4 Quadratics (2)") == [["Student", "1(a)", "Total", "Max"], ["Teo", 1, 1, 2]]
    rows = sheet("Rows")
    assert [r[:2] for r in rows[1:]] == [["Tan Wei Ling", "Sec 4 Quadratics"]] * 2 + [["Ng", "Narrative essay: [draft] * 2026/27 — a title long enough to be cut"]] * 2 \
        + [["Lim", "Sec 4 Quadratics"]] * 3 + [["Ong", "Quick mark"], ["Teo", "Sec 4 Quadratics"]]


def test_rubric_rows_sheet_keeps_the_truncated_transcription():
    long = "word " * 200
    rec = _record("Ng", 3, [_row("Content", "5 / 5", 5, 5)], 5, 5, 5, kind="rubric", transcription=long)
    rec.rows[0].student_answer = "See transcription (page 2)"
    wb = load_workbook(io.BytesIO(render_xlsx([rec])))
    cell = [[c.value for c in r] for r in wb["Rows"].iter_rows()][1][4]
    assert cell.startswith("word word") and cell.endswith("…") and len(cell) == 601


def test_bundle_zip_has_one_docx_per_record_and_the_markbook():
    assert record_filename("Tan Wei Ling") == "tan-wei-ling-marking-record.docx"
    assert record_filename("  Ürün / 3B  ") == "urun-3b-marking-record.docx"
    assert record_filename("***", 7) == "script-7-marking-record.docx" and record_filename("***") == "script-marking-record.docx"
    data = bundle_zip([REC_A, REC_B, _record("Lim", 3, [], 0, 0, 0), _record("陈伟", 4, [], 0, 0, 0)])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert names == ["tan-wei-ling-marking-record.docx", "lim-marking-record.docx", "lim-3-marking-record.docx",
                         "script-4-marking-record.docx", "markbook.xlsx"]
        assert z.read("tan-wei-ling-marking-record.docx")[:2] == b"PK"
        wb = load_workbook(io.BytesIO(z.read("markbook.xlsx")))
        assert wb["Sec 4 Quadratics"].max_row == 5


def test_formula_looking_text_is_stored_as_text_not_formula():
    rows = [_row("1(a)", "=2+2 (teacher)", 2), RecordRow(key="1b", label="+1(b)", scheme_answer="-x = 3", student_answer="= 3.5",
                                                        justification="@sum", awarded="=cmd|' /C calc'!A0", teacher="", to_review=False,
                                                        awarded_marks=1, max_marks=2)]
    rec = _record("=Tan", 1, rows, 3, 3, 4)
    wb = load_workbook(io.BytesIO(render_xlsx([rec])))
    for ws in (wb["Sec 4 Quadratics"], wb["Rows"]):
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, str):
                    assert cell.data_type == "s", (ws.title, cell.coordinate, cell.value)
    rs = [[c.value for c in r] for r in wb["Rows"].iter_rows()]
    assert rs[2] == ["=Tan", "Sec 4 Quadratics", "+1(b)", "-x = 3", "= 3.5", "@sum", "=cmd|' /C calc'!A0", None]
    mb = [[c.value for c in r] for r in wb["Sec 4 Quadratics"].iter_rows()]
    assert mb[0][1:3] == ["1(a)", "+1(b)"] and mb[1][0] == "=Tan"


def test_control_characters_do_not_break_xlsx():
    rows = [RecordRow(key="1a", label="1(a)", scheme_answer="a\x00b", student_answer="x\x0c= 3\tok\nnext", justification="j\x1f",
                      awarded="2 / 2", teacher="", to_review=False, awarded_marks=2, max_marks=2)]
    from sms.records.builder import sanitise
    rec = _record("Tan\x0b", 1, [RecordRow(**{**r.__dict__, "scheme_answer": sanitise(r.scheme_answer),
                                               "student_answer": sanitise(r.student_answer), "justification": sanitise(r.justification)})
                                  for r in rows], 2, 2, 2)
    rec.student = sanitise(rec.student)
    wb = load_workbook(io.BytesIO(render_xlsx([rec])))
    assert [c.value for c in wb["Rows"][2]][:6] == ["Tan", "Sec 4 Quadratics", "1(a)", "ab", "x= 3\tok\nnext", "j"]
