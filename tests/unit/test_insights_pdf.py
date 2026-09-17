"""The insights PDF renders from statistics alone, and with the narrative when there is one."""
from sms.records.insights_pdf import _labels, _narrative, _styles, render_insights_pdf

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


def _texts(flowables):
    """Every piece of text in a story, in order — ReportLab keeps the source string on Paragraph."""
    for f in flowables:
        text = getattr(f, "text", None)
        if text:
            yield text
        nested = getattr(f, "_content", None) or getattr(f, "_flowables", None)
        if nested:
            yield from _texts(nested)
        rows = getattr(f, "_cellvalues", None)
        if rows:
            yield from _texts([cell for row in rows for cell in row])


def test_the_narrative_names_parts_and_students_the_way_the_tables_do():
    """A gap about "9b" and a table row about part "9(b)" are the same part, so the narrative uses
    the labels; and a named student is "#1 Tan Wei Ling", the same "#" the fallback prints."""
    report = {**REPORT_FIXTURE,
              "gaps": [{"part_ids": ["1b", "1a"], "title": "Hence questions",
                        "what_went_wrong": "Did not reuse 1(a)", "students_affected": 1}],
              "recommendations": [{"title": "Reteach", "detail": "Use it", "part_ids": ["1b"]}],
              "students_to_support": [{"reg_nos": [1, 9], "focus": "follow-through"}]}
    out = list(_texts(_narrative(report, NAMES, _labels(STATS_FIXTURE), _styles())))
    assert "Hence questions (1(b), 1(a))" in out
    assert "Reteach (1(b)): Use it" in out
    assert "#1 Tan Wei Ling, #9" in out            # the '#' is on both the named and the unknown
    assert not any("1b" in t for t in out)         # never the raw part id


def test_the_narrative_falls_back_to_the_raw_part_id_when_it_is_not_a_known_part():
    out = list(_texts(_narrative(
        {"gaps": [{"part_ids": ["7c"], "title": "T", "what_went_wrong": "w", "students_affected": 0}],
         "recommendations": [{"title": "R", "detail": "d", "part_ids": []}]},
        {}, _labels(STATS_FIXTURE), _styles())))
    assert "T (7c)" in out and "R (—): d" in out


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
