from sms.records.builder import REASON_TEXT, Record, RecordRow, build_record


def _part(q_id, label, total, mx, *, escalated=False, reason=None, teacher=None, extracted="x = 3", workings="",
          illegible=False, justification="M1 for the method; A1 for x = 3", answer="x = 3", marks=None, in_scheme=True):
    return {
        "q_id": q_id, "label": label, "question_text": f"Question {label}",
        "scheme": {"answer": answer, "marks": marks or [{"label": "M1", "marks": 1}, {"label": "A1", "marks": 1}], "notes": ""},
        "extracted": extracted, "workings": workings, "illegible": illegible,
        "awarded": [{"label": "M1", "marks": 1, "got": True, "why": ""}, {"label": "A1", "marks": 1, "got": total > 1, "why": ""}],
        "total": total, "max": mx, "justification": justification, "in_scheme": in_scheme, "confidence": 0.9,
        "escalated": escalated, "reason": reason, "queue_id": 7 if escalated else None, "teacher": teacher,
    }


def _detail_v2(parts, totals, **over):
    d = {
        "id": 5, "label": "Tan Wei Ling", "subject": "math", "context": "", "status": "needs_you",
        "created_at": "2026-09-15T03:04:05Z", "rubric": {"criterion_defs": []}, "pages": [], "marks": [],
        "marks_version": 2, "parts": parts, "scheme_kind": "mark_scheme", "assignment_id": 3,
        "assignment_title": "Sec 4 Quadratics", "totals": totals, "feedback": None,
        "job": {"status": "done", "attempts": 1, "error": None, "started_at": "2026-09-15T03:05:00Z",
                "finished_at": "2026-09-15T03:09:09Z"}, "run_id": "r2", "marked_at": "2026-09-15T03:06:07Z",
    }
    d.update(over)
    return d


def test_v2_rows_follow_the_parts_with_awarded_teacher_and_review_states():
    parts = [
        _part("1a", "1(a)", 2, 2),
        _part("1b", "1(b)", 0, 1, escalated=True, reason="not in scheme", in_scheme=False, marks=[{"label": "B1", "marks": 1}]),
        _part("2", "2", 1, 3, teacher={"allocations": [{"label": "M1", "got": True, "marks": 1}, {"label": "A1", "got": True, "marks": 2}], "total": 3}),
    ]
    rec = build_record(_detail_v2(parts, {"total": 5, "total_upper": 6, "total_max": 6}), {"title": "Sec 4 Quadratics"}, model="openai · gpt-5-mini")
    assert isinstance(rec, Record) and rec.title == "Sec 4 Quadratics" and rec.student == "Tan Wei Ling"
    assert rec.marked_at == "2026-09-15T03:06:07Z" and rec.model == "openai · gpt-5-mini" and rec.kind == "mark_scheme"
    assert [r.label for r in rec.rows] == ["1(a)", "1(b)", "2"]
    a, b, c = rec.rows
    assert isinstance(a, RecordRow)
    assert a.scheme_answer == "x = 3  [M1 A1]" and a.student_answer == "x = 3"
    assert a.justification == "M1 for the method; A1 for x = 3" and a.awarded == "2 / 2" and a.teacher == ""
    assert a.to_review is False and a.awarded_marks == 2 and a.max_marks == 2
    assert b.awarded == "Teacher to review" and b.to_review and b.awarded_marks is None
    assert b.justification == "Answer not in the scheme — different method" and b.scheme_answer == "x = 3  [B1]"
    assert c.awarded == "3 / 3 (teacher)" and c.teacher == "" and c.awarded_marks == 3 and c.to_review is False
    assert (rec.total_awarded, rec.total_upper, rec.total_max, rec.to_review_count) == (5, 6, 6, 1)
    assert rec.rubric_page is None and rec.submission_id == 5


def test_reason_mapping_illegible_and_truncation():
    long = "9" * 700
    parts = [
        _part("1a", "1(a)", 0, 2, escalated=True, reason="illegible", illegible=True, extracted="???"),
        _part("1b", "1(b)", 1, 2, escalated=True, reason="reviewer escalated"),
        _part("1c", "1(c)", 1, 2, escalated=True, reason="marker/reviewer disagree"),
        _part("1d", "1(d)", 1, 2, escalated=True, reason="low confidence"),
        _part("2", "2", 2, 2, extracted=long, workings="working"),
        _part("3", "3", 2, 2, extracted="ans", workings="step 1\nstep 2"),
    ]
    rec = build_record(_detail_v2(parts, {"total": 5, "total_upper": 12, "total_max": 12}), None)
    rows = {r.label: r for r in rec.rows}
    assert rows["1(a)"].student_answer == "(illegible)" and rows["1(a)"].justification == REASON_TEXT["illegible"] == "Unclear handwriting"
    assert rows["1(b)"].justification == "Marker and reviewer disagreed" == rows["1(c)"].justification
    assert rows["1(d)"].justification == "Low confidence"
    from sms.records.builder import reason_text
    assert reason_text("illegible transcription") == "Unclear handwriting" == reason_text("Illegible")
    assert reason_text("low marker confidence") == "Low confidence"
    assert reason_text("something new") == "Teacher to review" == reason_text(None)
    assert rows["2"].student_answer.endswith("…") and len(rows["2"].student_answer) == 601
    assert rows["3"].student_answer == "ans\nWorkings: step 1\nstep 2"
    assert rec.to_review_count == 4 and rec.marked_at == "2026-09-15T03:06:07Z"


def test_title_falls_back_to_the_template_then_the_context_then_the_script():
    d = _detail_v2([], {"total": 0, "total_upper": 0, "total_max": 0}, assignment_title=None, context="Worksheet 3", job=None,
                   marked_at=None)
    assert build_record(d, {"title": "From template"}).title == "From template"
    assert build_record(d, None).title == "Worksheet 3"
    d["context"] = ""
    rec = build_record(d, None)
    assert rec.title == "Script 5" and rec.marked_at == "2026-09-15T03:04:05Z" and rec.model == ""


def test_rubric_record_has_band_rows_and_a_rubric_page():
    bands = [{"band": "A", "marks": 5, "descriptor": "Rich detail"}, {"band": "B", "marks": 3, "descriptor": "Some detail"}]
    parts = [
        {"q_id": "Content", "label": "Content", "question_text": "Essay", "scheme": {"criterion": "Content", "bands": bands},
         "extracted": "My day...", "workings": "", "illegible": False, "band": "A", "descriptor_met": "Rich detail", "total": 5,
         "max": 5, "justification": "Vivid throughout", "in_scheme": True, "confidence": 0.9, "escalated": False,
         "reason": None, "queue_id": None, "teacher": None},
        {"q_id": "Language", "label": "Language", "question_text": "Essay", "scheme": {"criterion": "Language", "bands": bands},
         "extracted": "My day...", "workings": "", "illegible": False, "band": "B", "descriptor_met": "", "total": 3,
         "max": 5, "justification": "Tense slips", "in_scheme": True, "confidence": 0.5, "escalated": True,
         "reason": "low confidence", "queue_id": 9, "teacher": None},
    ]
    rec = build_record(_detail_v2(parts, {"total": 8, "total_upper": 10, "total_max": 10}, scheme_kind="rubric"), None)
    assert rec.kind == "rubric"
    a, b = rec.rows
    assert a.scheme_answer == "Content\nA (5): Rich detail\nB (3): Some detail"
    assert a.justification == "Band A: Vivid throughout" and a.awarded == "5 / 5"
    assert b.awarded == "Teacher to review" and b.justification == "Low confidence"
    assert rec.rubric_page == [{"criterion": "Content", "bands": bands, "awarded_band": "A"},
                               {"criterion": "Language", "bands": bands, "awarded_band": None}]


def test_v1_rows_summarise_criteria():
    d = {
        "id": 8, "label": "Lim", "subject": "math", "context": "Worksheet 3", "status": "done", "created_at": "2026-09-15T03:04:05Z",
        "rubric": {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}, {"id": "c2", "description": "answer", "max_score": 3}]},
        "pages": [], "marks_version": 1, "parts": [], "scheme_kind": None, "assignment_id": None, "assignment_title": None,
        "marks": [
            {"q_id": "q1", "criterion_scores": [2, 1], "total": 3, "max": 5, "confidence": 0.9, "evidence": "x = 3", "rationale": "clear",
             "escalated": False, "reason": None, "queue_id": None, "teacher_scores": None},
            {"q_id": "q2", "criterion_scores": [1, 1], "total": 2, "max": 5, "confidence": 0.3, "evidence": "", "rationale": "hmm",
             "escalated": True, "reason": "low marker confidence", "queue_id": 4, "teacher_scores": None},
            {"q_id": "q3", "criterion_scores": [0, 0], "total": 0, "max": 5, "confidence": 0.3, "evidence": "e", "rationale": "r",
             "escalated": False, "reason": None, "queue_id": None, "teacher_scores": [2, 2]},
        ],
        "totals": {"total": 7, "total_upper": 10, "total_max": 15}, "feedback": None, "job": None, "run_id": "r1",
        "marked_at": "2026-09-15T04:00:00Z",
    }
    rec = build_record(d, None)
    assert rec.kind == "criteria" and rec.title == "Worksheet 3"
    q1, q2, q3 = rec.rows
    assert q1.label == "Q1" and q1.scheme_answer == "c1 method (2) · c2 answer (3)" and q1.student_answer == "x = 3"
    assert q1.justification == "clear\nc1 2/2 · c2 1/3" and q1.awarded == "3 / 5"
    assert q2.awarded == "Teacher to review" and q2.justification == "Low confidence"
    assert q3.awarded == "4 / 5 (teacher)" and q3.justification == "r\nc1 2/2 · c2 2/3"
    assert (rec.total_awarded, rec.total_upper, rec.total_max, rec.to_review_count) == (7, 10, 15, 1)
    assert rec.marked_at == "2026-09-15T04:00:00Z"
