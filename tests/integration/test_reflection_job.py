from sms.learning.reflection_job import activate_note, run_reflection
from sms.memory.db import Database
from sms.schemas.reflection import ExemplarCase, ReflectionUpdate, RubricNote


class StubReflectionAgent:
    def __init__(self, canned):
        self._canned = canned

    def run(self, user_input):
        self.last_input = user_input
        return self._canned


UPDATE = ReflectionUpdate(
    rubric_notes=[RubricNote(subject="math", note="Always require units in final answers.", source_run_ids=["r1", "r2"])],
    exemplar_cases=[ExemplarCase(subject="math", topic="algebra", q_id="q3",
                                 answer_text="x = 3 (units: cm)", awarded=5, max_score=5,
                                 why_it_matters="States units explicitly")],
)


def _add_correction(db, run_id):
    db.execute(
        "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) VALUES (?, ?, ?, ?, ?)",
        (run_id, "q1", 2, 3, "student stated units; agent missed"),
    )


def test_reflection_writes_draft_rows(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute(
        "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, final_status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("r1", "complete", "math", "{}", '{"questions": [{"q_id": "q1", "transcribed_answer": "x=3"}]}', "complete"),
    )
    db.execute(
        "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, final_status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("r2", "complete", "math", "{}", '{"questions": [{"q_id": "q1", "transcribed_answer": "y=5"}]}', "complete"),
    )
    _add_correction(db, "r1")
    _add_correction(db, "r2")
    agent = StubReflectionAgent(UPDATE)
    result = run_reflection(db=db, agent=agent, subject="math", lookback_days=7)
    assert result == 1
    rows = db.query("SELECT * FROM rubric_notes WHERE status = 'draft'")
    assert rows and "units" in rows[0]["note"]
    exemplars = db.query("SELECT * FROM exemplar_cases WHERE status = 'draft'")
    assert exemplars and exemplars[0]["awarded"] == 5


def test_activation_flips_status(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'note', 'draft')")
    note_id = db.query("SELECT id FROM rubric_notes")[0]["id"]
    activate_note(db, note_id)
    row = db.query("SELECT status FROM rubric_notes WHERE id = ?", (note_id,))[0]
    assert row["status"] == "active"


def test_reflection_noop_without_corrections(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    agent = StubReflectionAgent(UPDATE)
    result = run_reflection(db=db, agent=agent, subject="math", lookback_days=7)
    assert result == 0
    assert not hasattr(agent, "last_input")


def test_reflection_sees_cli_resolved_corrections(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute(
        "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, final_status) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("r1", "complete", "math", "{}", '{"questions": [{"q_id": "q1", "transcribed_answer": "x=3"}]}', "escalated"),
    )
    db.execute(
        "INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) "
        "VALUES (?, ?, ?, ?, ?)",
        ("r1", "q1", 2, 3, "teacher override"),
    )
    agent = StubReflectionAgent(UPDATE)
    result = run_reflection(db=db, agent=agent, subject="math", lookback_days=7)
    assert result == 1
    assert agent.last_input.corrections[0].agent_mark == 2


def test_reflection_uses_the_whole_transcription_for_a_rubric_run(tmp_path):
    """A rubric marks the response as one, so a correction on a criterion carries every transcribed
    answer, not a lookup of the criterion name among the question ids."""
    db = Database(path=str(tmp_path / "s.db"))
    rubric_json = '{"scheme_kind": "rubric", "questions": [], "scheme": [], "notes": ""}'
    db.execute(
        "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, extracted_json, final_status) VALUES (?, ?, ?, ?, ?, ?)",
        ("r1", "complete", "language", rubric_json,
         '{"questions": [{"q_id": "1", "transcribed_answer": "Once upon a time"}, {"q_id": "2", "transcribed_answer": "The end."}]}',
         "complete"),
    )
    db.execute("INSERT INTO teacher_corrections (run_id, q_id, agent_mark, teacher_mark, reason) VALUES ('r1', 'Content', 3, 5, 'richer')")
    agent = StubReflectionAgent(UPDATE)
    run_reflection(db=db, agent=agent, subject="language", lookback_days=7)
    c = agent.last_input.corrections[0]
    assert c.q_id == "Content" and c.extracted_answer == "Once upon a time\n\nThe end."
