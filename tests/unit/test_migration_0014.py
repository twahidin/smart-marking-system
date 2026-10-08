import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from sms.memory.db import Database


def test_0014_adds_events_stage_reflect_days_and_student_corrections(tmp_path):
    db = Database(path=str(tmp_path / "m.db"))
    insp = inspect(db.engine)
    assert insp.has_table("marking_events") and insp.has_table("student_corrections")
    assert "stage" in {c["name"] for c in insp.get_columns("submissions")}
    assert "reflect_days" in {c["name"] for c in insp.get_columns("settings")}
    assert "reflect_days" in {c["name"] for c in insp.get_columns("class_assignments")}
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status) VALUES ('s', 'math', '', '{}', 'queued') RETURNING id")
    db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1a', 'sign', 'x = -2', 'submitted')", {"s": sid})
    with pytest.raises(IntegrityError):
        db.execute("INSERT INTO student_corrections (submission_id, q_id, reason, text, status) VALUES (:s, '1a', 'sign', 'again', 'submitted')", {"s": sid})
