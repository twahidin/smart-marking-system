import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from sms.memory.db import Database
from sms.memory.migrate import upgrade


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
    assert "original_total" in {c["name"] for c in insp.get_columns("student_corrections")}


def _backfill_check(engine):
    """At 0013 one class set was already released and one was not; 0014 must close the reflection window of
    the released one (reflect_days = 0) and leave the other following the Settings default (NULL)."""
    upgrade(engine, "0013")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO classes (id, name, code) VALUES (1, '4E2', 'ABCD')"))
        conn.execute(text("INSERT INTO class_assignments (id, class_id, template_id, title, status, released_at) VALUES "
                          "(1, 1, 1, 'old', 'released', CURRENT_TIMESTAMP), (2, 1, 1, 'new', 'open', NULL)"))
    upgrade(engine, "head")
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT title, reflect_days FROM class_assignments")).all())
    assert rows == {"old": 0, "new": None}


def test_0014_closes_the_window_of_sets_released_before_it(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    try:
        _backfill_check(engine)
    finally:
        engine.dispose()


@pytest.mark.skipif(not os.environ.get("SMS_TEST_PG_URL"), reason="SMS_TEST_PG_URL not set")
def test_0014_backfill_on_postgres():
    engine = create_engine(os.environ["SMS_TEST_PG_URL"])
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        _backfill_check(engine)
    finally:
        engine.dispose()
