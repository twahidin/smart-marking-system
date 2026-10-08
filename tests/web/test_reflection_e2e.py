"""Reflect and correct end to end: a student sends a correction, the remark job re-marks it with a fake
pipeline, the teacher accepts and releases, and the new mark reaches the student view, the records'
released marks and the marks CSV. Once for a mark-scheme assignment and once for a rubric one."""
import pytest

from sms.schemas.marking_v2 import AllocationMark, MarkedScriptV2, PartMark, ReviewedScriptV2, RubricMark
from sms.web.services.student_corrections import released_marks
from sms.worker.remark_job import run_remark_job
from tests.unit.test_remark_job import _Pipe
from tests.web.seed_v2 import QUESTIONS, RUBRIC, RUBRIC_QUESTIONS, SCHEME, seed_v2
from tests.web.test_student_api import RUBRIC as CRITERIA, _class

CASES = {
    # kind: (questions, scheme, part the student corrects, its key, the Marker's re-mark, total before, total after)
    "mark_scheme": (QUESTIONS, SCHEME, "1b", "1b",
                    MarkedScriptV2(kind="mark_scheme", parts=[PartMark(q_id="1b", awarded=[AllocationMark(label="B1", marks=1, got=True)],
                                                                       total=1, justification="9 now")]), 3, 4),
    "rubric": (RUBRIC_QUESTIONS, RUBRIC, "Language", "language",
               MarkedScriptV2(kind="rubric", rubric=[RubricMark(criterion="Language", band="A", marks=5, justification="accurate now")]), 7, 10),
}


@pytest.mark.parametrize("kind", list(CASES))
def test_correction_round_trip(auth, client, app, kind):
    questions, scheme, q_id, key, remarked, before, after = CASES[kind]
    db = app.state.db
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x", "rpm_limit": 60, "confidence_threshold": 0})
    t = auth.post("/api/assignments", json={"title": "Worksheet", "subject": "math", "context": "", "rubric": CRITERIA,
                                            "scheme_kind": kind, "questions": questions, "scheme": scheme}).json()
    c = _class(auth)
    ca = auth.post(f"/api/classes/{c['id']}/assignments", json={"template_id": t["id"], "due_at": "2026-09-30T08:00:00Z"}).json()
    auth.put(f"/api/classes/{c['id']}/assignments/{ca['id']}", json={"title": ca["title"], "due_at": ca["due_at"],
                                                                      "allow_student_uploads": True, "status": "open"})
    sid, _ = seed_v2(app, kind=kind, label="#1 Tan", assignment_id=t["id"], run_id=f"r-{kind}", queue={})
    db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' "
               "WHERE id = :id", {"a": ca["id"], "s": c["students"][0]["id"], "id": sid})
    assert auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release").status_code == 200

    # the student sends one correction
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    r = client.post(f"/api/student/assignments/{ca['id']}/corrections", data={"q_id": q_id, "reason": "misread", "text": "my corrected answer"})
    assert r.status_code == 201
    cid = r.json()["id"]

    # the worker re-marks it
    pipe = _Pipe(remarked, ReviewedScriptV2(verdicts=[]))
    run_remark_job(db, app.state.storage, app.state.settings_store, cid, pipeline_factory=lambda **k: pipe)
    assert pipe.marker.calls[0].extracted.questions[0].transcribed_answer == "my corrected answer"

    # the teacher accepts and releases
    auth.post("/api/auth/login", json={"password": "letmein"})
    listed = auth.get(f"/api/review/corrections?class_assignment_id={ca['id']}").json()
    assert [(x["id"], x["status"]) for x in listed] == [(cid, "remarked")]
    new_mark = listed[0]["remark_total"]
    assert new_mark > listed[0]["original_total"] and listed[0]["original_max"] == listed[0]["remark_max"]
    assert auth.post(f"/api/corrections/{cid}/accept").status_code == 200
    assert auth.post(f"/api/class-assignments/{ca['id']}/release-corrections").json() == {"released": 1}

    # the student sees the new mark, and nothing of the Marker's reasoning
    client.cookies.clear()
    client.post("/api/student/session", json={"code": c["code"], "reg_no": 1})
    got = client.get(f"/api/student/assignments/{ca['id']}").json()
    assert got["reflection"]["parts"][key] == {"can_correct": False, "status": "released", "new_mark": new_mark}
    assert "Marker:" not in str(got)

    # records and the marks CSV carry it
    assert released_marks(db, sid) == {key: {"total": new_mark, "max": listed[0]["remark_max"]}}
    auth.post("/api/auth/login", json={"password": "letmein"})
    header, first = auth.get(f"/api/classes/{c['id']}/assignments/{ca['id']}/marks.csv").text.splitlines()[:2]
    cells = dict(zip(header.split(","), first.split(",")))
    assert (cells["total"], cells["after_reflection_total"]) == (str(before), str(after))
