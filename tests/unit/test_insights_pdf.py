"""The insights PDF renders from statistics alone, and with the narrative when there is one."""
from sms.records.insights_pdf import render_insights_pdf

STATS_FIXTURE = {
    "n_students": 3, "n_marked": 2, "n_pending": 1,
    "totals": {"mean": 2.5, "median": 2.5, "max": 3,
               "buckets": [{"from": 0, "to": 0, "n": 0}, {"from": 1, "to": 1, "n": 0},
                           {"from": 2, "to": 2, "n": 1}, {"from": 3, "to": 3, "n": 1}]},
    "parts": [
        {"q_id": "1a", "label": "1(a)", "max": 2, "attempted": 2, "mean_pct": 75.0, "full": 1, "zero": 0,
         "allocations": [{"label": "M1", "lost": 0}, {"label": "A1", "lost": 1}],
         "not_in_scheme": 0, "illegible": 0, "pending": 0},
        {"q_id": "1b", "label": "1(b)", "max": 1, "attempted": 2, "mean_pct": 50.0, "full": 1, "zero": 1,
         "allocations": [{"label": "B1", "lost": 1}], "not_in_scheme": 0, "illegible": 0, "pending": 1},
    ],
    "weakest": ["1b", "1a"],
    "most_lost": [{"q_id": "1b", "label": "B1", "lost": 1, "of": 2},
                  {"q_id": "1a", "label": "A1", "lost": 1, "of": 2}],
    "students": [{"student_id": 11, "reg_no": 1, "name": "Tan Wei Ling", "total": 2, "max": 3, "weak_parts": ["1b"]},
                 {"student_id": 12, "reg_no": 2, "name": "Muhammad Danish", "total": 3, "max": 3, "weak_parts": []}],
}

REPORT_FIXTURE = {
    "summary": "The class secured the method in 1(a); follow-through in 1(b) is the gap.",
    "strengths": ["Rearranging 3x = 9 is secure", "Working is shown before the answer"],
    "gaps": [{"part_ids": ["1b"], "title": "Hence questions", "what_went_wrong": "Did not reuse 1(a)",
              "students_affected": 1}],
    "recommendations": [{"title": "Reteach follow-through", "detail": "Use 1(b) as the worked example",
                         "part_ids": ["1b"]}],
    "students_to_support": [{"reg_nos": [1, 9], "focus": "follow-through from a previous part"}],
}

CA = {"id": 1, "title": "Worksheet 3", "class_name": "4E2"}
NAMES = {1: "Tan Wei Ling", 2: "Muhammad Danish"}


def test_insights_pdf_renders():
    data = render_insights_pdf(CA, STATS_FIXTURE, REPORT_FIXTURE, NAMES)
    assert data[:4] == b"%PDF" and len(data) > 2000
    # statistics alone still render: the narrative sections are replaced by a note
    bare = render_insights_pdf(CA, STATS_FIXTURE, None, NAMES)
    assert bare[:4] == b"%PDF" and len(bare) > 2000
    assert len(bare) < len(data)


def test_insights_pdf_survives_an_empty_assignment():
    """Nothing marked: no parts, no students, no totals — the PDF is still a PDF."""
    empty = {"n_students": 0, "n_marked": 0, "n_pending": 0,
             "totals": {"mean": None, "median": None, "max": 0, "buckets": []},
             "parts": [], "weakest": [], "most_lost": [], "students": []}
    data = render_insights_pdf({"id": 2, "title": "Worksheet 4"}, empty, None, {})
    assert data[:4] == b"%PDF" and len(data) > 1000


def test_insights_pdf_escapes_markup_in_text():
    """Teacher-facing text goes through ReportLab's mini-HTML, so < & > must not blow it up."""
    stats = {**STATS_FIXTURE,
             "parts": [{**STATS_FIXTURE["parts"][0], "label": "1(a) <x & y>"}],
             "students": [{"student_id": 11, "reg_no": 1, "name": "A & B <c>", "total": 2, "max": 3,
                           "weak_parts": []}]}
    report = {**REPORT_FIXTURE, "summary": "Marks < 50% & falling <b>",
              "strengths": ["x < y & z"], "gaps": [{**REPORT_FIXTURE["gaps"][0], "title": "a & b <c>"}]}
    data = render_insights_pdf({"id": 3, "title": "Ratio & Proportion <S1>"}, stats, report, {1: "A & B <c>"})
    assert data[:4] == b"%PDF" and len(data) > 2000
