import io
import zipfile

from openpyxl import load_workbook

from sms.records.builder import Record, RecordRow
from sms.records.bundle import bundle_zip, record_filename
from sms.records.xlsx import render_xlsx


def _row(label, awarded, marks, mx=2, to_review=False):
    return RecordRow(key=label, label=label, scheme_answer="ans", student_answer="x", justification="j", awarded=awarded,
                     teacher="", to_review=to_review, awarded_marks=marks, max_marks=mx)


def _record(student, sid, rows, total, upper, mx, review=0):
    return Record(title="Sec 4 Quadratics", student=student, marked_at="2026-09-15T03:06:07Z", model="m", rows=rows,
                  total_awarded=total, total_upper=upper, total_max=mx, to_review_count=review, rubric_page=None,
                  submission_id=sid, kind="mark_scheme")


REC_A = _record("Tan Wei Ling", 1, [_row("1(a)", "2 / 2", 2), _row("1(b)", "Teacher to review", None, to_review=True)], 2, 4, 4, 1)
REC_B = _record("Lim", 2, [_row("1(a)", "1 / 2", 1), _row("1(b)", "2 / 2 (teacher)", 2), _row("2", "3 / 3", 3, 3)], 6, 6, 7)


def test_markbook_and_rows_sheets():
    data = render_xlsx([REC_A, REC_B])
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Markbook", "Rows"]
    mb = wb["Markbook"]
    rows = [[c.value for c in r] for r in mb.iter_rows()]
    assert rows[0] == ["Student", "1(a)", "1(b)", "2", "Total", "Max"]
    assert rows[1] == ["Tan Wei Ling", 2, "Review", None, "2–4", 4]
    assert rows[2] == ["Lim", 1, 2, 3, 6, 7]
    rs = wb["Rows"]
    rows = [[c.value for c in r] for r in rs.iter_rows()]
    assert rows[0] == ["Student", "Question & part", "Marking scheme answer", "Student's answer (extracted)", "Justification",
                       "Awarded mark", "Teacher's mark"]
    assert len(rows) == 1 + 2 + 3
    assert rows[2] == ["Tan Wei Ling", "1(b)", "ans", "x", "j", "Teacher to review", None]
    assert rows[4] == ["Lim", "1(b)", "ans", "x", "j", "2 / 2 (teacher)", None]


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
        assert wb["Markbook"].max_row == 5


def test_formula_looking_text_is_stored_as_text_not_formula():
    rows = [_row("1(a)", "=2+2 (teacher)", 2), RecordRow(key="1b", label="+1(b)", scheme_answer="-x = 3", student_answer="= 3.5",
                                                        justification="@sum", awarded="=cmd|' /C calc'!A0", teacher="", to_review=False,
                                                        awarded_marks=1, max_marks=2)]
    rec = _record("=Tan", 1, rows, 3, 3, 4)
    wb = load_workbook(io.BytesIO(render_xlsx([rec])))
    for ws in (wb["Markbook"], wb["Rows"]):
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, str):
                    assert cell.data_type == "s", (ws.title, cell.coordinate, cell.value)
    rs = [[c.value for c in r] for r in wb["Rows"].iter_rows()]
    assert rs[2] == ["=Tan", "+1(b)", "-x = 3", "= 3.5", "@sum", "=cmd|' /C calc'!A0", None]
    mb = [[c.value for c in r] for r in wb["Markbook"].iter_rows()]
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
    assert [c.value for c in wb["Rows"][2]][:5] == ["Tan", "1(a)", "ab", "x= 3\tok\nnext", "j"]
