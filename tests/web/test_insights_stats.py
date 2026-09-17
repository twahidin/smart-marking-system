"""compute_stats / select_samples over seeded v2 runs (web fixtures: `app` builds the schema)."""
from sms.web.services.class_assignments import get_class_assignment
from sms.web.services.insights import WEAKEST, compute_stats, select_samples

from tests.web.seed_v2 import QUESTIONS as V2_QUESTIONS, SCHEME as V2_SCHEME, _alloc, part, seed_v2
from tests.web.test_class_assignments_api import _class_with_students, _link, _seed_v1, _template, _v1_mark

DANISH_PARTS = [part("1a", [_alloc("M1", 1, True, "3x=9 seen"), _alloc("A1", 1, False, "x = 6")], 1, "M1 only"),
                part("1b", [_alloc("B1", 1, True, "9")], 1, "B1 for 9"),
                part("2", [_alloc("M1", 1, True), _alloc("A1", 2, True)], 3, "fully expanded")]


def _seed_class(auth, app):
    """Tan (1a 2/2, 1b 0/1, part 2 escalated), Danish (1a 1/2, 1b 1/1, 2 3/3), Priya (not handed in)."""
    t = _template(auth, questions=V2_QUESTIONS, scheme=V2_SCHEME)
    c = _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish", "Priya Nair"))
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}",
             json={"title": ca["title"], "due_at": None, "allow_student_uploads": True, "status": "open"})
    tan, danish, _priya = c["students"]
    sid_tan, qids = seed_v2(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="r-tan")
    sid_dan, _ = seed_v2(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="r-dan",
                         parts=DANISH_PARTS, queue={})
    _link(app, sid_tan, ca["id"], tan["id"])
    _link(app, sid_dan, ca["id"], danish["id"])
    return t, c, ca, qids


def _stats(app, c, ca):
    row = get_class_assignment(app.state.db, c["id"], ca["id"])
    return row, compute_stats(app.state.db, app.state.jobs, row)


def test_compute_stats_from_marked_scripts(auth, app):
    t, c, ca, qids = _seed_class(auth, app)
    _row, st = _stats(app, c, ca)
    assert (st["n_students"], st["n_marked"], st["n_pending"]) == (3, 2, 1)
    p = {x["q_id"]: x for x in st["parts"]}
    assert p["1a"]["attempted"] == 2 and p["1a"]["mean_pct"] == 75.0 and p["1a"]["full"] == 1
    assert p["1a"]["allocations"] == [{"label": "M1", "lost": 0}, {"label": "A1", "lost": 1}]
    assert p["1b"]["mean_pct"] == 50.0 and p["1b"]["zero"] == 1
    assert p["2"]["pending"] == 1 and p["2"]["attempted"] == 1      # Tan's part 2 is still in the queue
    assert st["weakest"][0] == "1b"                                 # ties broken by scheme order; min-attempts rule disabled below 5 students
    assert st["most_lost"][0] == {"q_id": "1a", "label": "A1", "lost": 1, "of": 2} or st["most_lost"][0]["q_id"] == "1b"
    s = {x["reg_no"]: x for x in st["students"]}
    assert s[1]["weak_parts"] == ["1b"] and s[1]["name"] == "Tan Wei Ling" and s[2]["total"] == 5
    assert st["totals"]["max"] == 6 and len(st["totals"]["buckets"]) == 5
    # the labels are teacher-facing and the parts keep scheme order
    assert [x["label"] for x in st["parts"]] == ["1(a)", "1(b)", "2"]
    # full marks land in the last bucket, and every marked script lands in exactly one
    assert st["totals"]["buckets"][-1]["to"] == 6 and sum(b["n"] for b in st["totals"]["buckets"]) == 2
    assert st["parts"][2]["not_in_scheme"] == 1                      # Tan's part 2 was marked out of scheme


def test_compute_stats_counts_a_resolved_part_with_the_teachers_marks(auth, app):
    t, c, ca, qids = _seed_class(auth, app)
    auth.post(f"/api/queue/{qids['2']}/resolve",
              json={"allocations": [{"label": "M1", "got": True}, {"label": "A1", "got": False}], "reason": "method only"})
    _row, st = _stats(app, c, ca)
    p = {x["q_id"]: x for x in st["parts"]}
    assert p["2"]["pending"] == 0 and p["2"]["attempted"] == 2
    assert p["2"]["mean_pct"] == 66.7                                # Tan 1/3, Danish 3/3
    assert p["2"]["allocations"] == [{"label": "M1", "lost": 0}, {"label": "A1", "lost": 1}]
    s = {x["reg_no"]: x for x in st["students"]}
    assert s[1]["weak_parts"] == ["1b", "2"] and s[1]["total"] == 3


def test_compute_stats_for_a_criteria_template_uses_the_marked_questions(auth, app):
    """A criteria template has no per-question scheme, so the parts are the questions the scripts
    answered (v1 runs key their marks by q_id), each worth the rubric's total."""
    t = _template(auth, scheme_kind="criteria", questions=[], scheme=[])   # RUBRIC: one criterion, max 2
    c = _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish", "Priya Nair"))
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    tan, danish, _priya = c["students"]
    sid_tan = _seed_v1(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="v1-tan",
                       marks=[_v1_mark("q1", 2), _v1_mark("q2", 1)])
    sid_dan = _seed_v1(app, label="#2 Muhammad Danish", assignment_id=t["id"], run_id="v1-dan",
                       marks=[_v1_mark("q2", 0), _v1_mark("q3", 2)])
    _link(app, sid_tan, ca["id"], tan["id"])
    _link(app, sid_dan, ca["id"], danish["id"])
    _row, st = _stats(app, c, ca)
    assert (st["n_students"], st["n_marked"], st["n_pending"]) == (3, 2, 0)
    assert [(x["q_id"], x["label"], x["max"]) for x in st["parts"]] == [("q1", "Q1", 2), ("q2", "Q2", 2), ("q3", "Q3", 2)]
    p = {x["q_id"]: x for x in st["parts"]}
    assert (p["q1"]["attempted"], p["q2"]["attempted"], p["q3"]["attempted"]) == (1, 2, 1)
    assert p["q2"]["mean_pct"] == 25.0 and p["q2"]["zero"] == 1 and p["q2"]["full"] == 0
    assert st["weakest"] == ["q2", "q1", "q3"] and st["most_lost"] == []   # criteria marks have no allocations
    assert st["totals"]["max"] == 6                                        # 2 marks x the 3 questions answered
    s = {x["reg_no"]: x for x in st["students"]}
    assert (s[1]["total"], s[2]["total"]) == (3, 2) and s[2]["weak_parts"] == ["q2"]
    assert all(x["total"] <= x["max"] for x in st["students"])


def test_weakest_is_a_shortlist_not_the_whole_paper_ranked(auth, app):
    """`weakest` is what the panel highlights and what the narrative reads samples from, so a long
    paper lists only its worst WEAKEST parts — every part below every other part is not a finding."""
    t = _template(auth, scheme_kind="criteria", questions=[], scheme=[])   # RUBRIC: one criterion, max 2
    c = _class_with_students(auth, names=("Tan Wei Ling", "Muhammad Danish"))
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"]}).json()
    qs = [f"q{i:02d}" for i in range(1, 13)]
    scores = [0] * 8 + [1, 1, 2, 2]                                  # 0%, then 50%, then full marks
    sid = _seed_v1(app, label="#1 Tan Wei Ling", assignment_id=t["id"], run_id="v1-long",
                   marks=[_v1_mark(q, s) for q, s in zip(qs, scores)])
    _link(app, sid, ca["id"], c["students"][0]["id"])
    _row, st = _stats(app, c, ca)
    assert len(st["parts"]) == 12                                    # every part still has its row
    assert st["weakest"] == qs[:WEAKEST] and len(st["weakest"]) == 8


def test_select_samples_is_anonymous(auth, app):
    t, c, ca, _qids = _seed_class(auth, app)
    priya = c["students"][2]
    long_answer = "x" * 500
    extracted = {"questions": [{"q_id": q, "transcribed_answer": long_answer if q == "1a" else "0", "workings": "",
                                "confidence": 0.5, "needs_human_transcription": False} for q in ("1a", "1b", "2")]}
    parts = [part("1a", [_alloc("M1", 1, False), _alloc("A1", 1, False)], 0, "no creditworthy method"),
             part("1b", [_alloc("B1", 1, False)], 0, "wrong"),
             part("2", [_alloc("M1", 1, False), _alloc("A1", 2, False)], 0, "not expanded")]
    sid, _ = seed_v2(app, label="#3 Priya Nair", assignment_id=t["id"], run_id="r-priya", parts=parts,
                     extracted=extracted, queue={})
    _link(app, sid, ca["id"], priya["id"])
    row, st = _stats(app, c, ca)
    assert st["weakest"][:2] == ["1b", "1a"]                         # 1b 33.3%, then 1a 50.0% before 2 (scheme order)
    rows = select_samples(app.state.db, app.state.jobs, row, st, per_part=10, max_parts=2)
    # only the weakest parts, weakest part first, lowest score first inside a part, ties in register order
    assert [(r["part"], r["reg_no"]) for r in rows] == [("1b", 1), ("1b", 3), ("1b", 2), ("1a", 3), ("1a", 2), ("1a", 1)]
    assert all("name" not in r and "student_id" not in r for r in rows)
    assert all(len(r["extracted"]) <= 300 for r in rows)
    assert rows[0] == {"part": "1b", "reg_no": 1, "extracted": "6", "awarded": 0, "max": 1,
                       "justification": "B1 lost: 6 not 9"}
    assert rows[3]["extracted"] == "x" * 300 and rows[3]["awarded"] == 0 and rows[3]["max"] == 2
    # per_part caps each part's rows
    capped = select_samples(app.state.db, app.state.jobs, row, st, per_part=1, max_parts=4)
    assert [(r["part"], r["reg_no"]) for r in capped] == [("1b", 1), ("1a", 3), ("2", 3)]
