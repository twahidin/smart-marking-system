from sqlalchemy import inspect

from sms.memory.db import Database


def test_0015_adds_a_nullable_subject_to_classes(tmp_path):
    db = Database(path=str(tmp_path / "m.db"))
    cols = {c["name"]: c for c in inspect(db.engine).get_columns("classes")}
    assert "subject" in cols and cols["subject"]["nullable"] is True
    cid = db.insert("INSERT INTO classes (name, code) VALUES ('4E2', 'ABCD') RETURNING id")
    assert db.query("SELECT subject FROM classes WHERE id = :i", {"i": cid})[0]["subject"] is None
