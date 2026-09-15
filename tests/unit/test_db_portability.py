import pytest

from sms.memory.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(path=str(tmp_path / "s.db"))


def test_tables_exist_after_construct(db):
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"marking_runs", "teacher_corrections", "rubric_notes", "exemplar_cases",
            "extraction_cache", "agent_metrics", "teacher_queue", "alembic_version"} <= names


def test_qmark_tuple_params(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES (?, ?, ?)", ("math", "n1", "draft"))
    rows = db.query("SELECT note FROM rubric_notes WHERE subject = ?", ("math",))
    assert [r["note"] for r in rows] == ["n1"]


def test_named_dict_params(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES (:s, :n, :st)",
               {"s": "math", "n": "n2", "st": "draft"})
    rows = db.query("SELECT note FROM rubric_notes WHERE subject = :s", {"s": "math"})
    assert [r["note"] for r in rows] == ["n2"]


def test_insert_returning_id(db):
    new_id = db.insert("INSERT INTO rubric_notes (subject, note, status) VALUES (:s, :n, 'draft') RETURNING id",
                       {"s": "math", "n": "x"})
    assert isinstance(new_id, int) and new_id >= 1


def test_execute_returns_rowcount(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'a', 'draft')")
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'b', 'draft')")
    assert db.execute("UPDATE rubric_notes SET status = 'active' WHERE subject = 'math'") == 2


def test_url_constructor_and_postgres_scheme_normalisation(tmp_path):
    d = Database(url=f"sqlite:///{tmp_path / 'u.db'}")
    assert d.is_sqlite
    d2 = Database.__new__(Database)
    assert d2._normalise_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert d2._normalise_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_created_at_default_is_populated(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'a', 'draft')")
    row = db.query("SELECT created_at FROM rubric_notes")[0]
    assert row["created_at"]


def test_qmark_inside_string_literal_is_not_a_placeholder(db):
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'why?', 'draft')")
    rows = db.query(
        "SELECT note FROM rubric_notes WHERE subject = ? AND note != 'unused?'",
        ("math",),
    )
    assert [r["note"] for r in rows] == ["why?"]


def test_qmark_param_count_mismatch_raises_value_error(db):
    with pytest.raises(ValueError) as exc_info:
        db.query("SELECT note FROM rubric_notes WHERE subject = ? AND note = ?", ("math",))
    message = str(exc_info.value)
    assert "2" in message and "1" in message


def test_web_tables_exist(db):
    names = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"settings", "submissions", "pages", "jobs", "worker_heartbeat"} <= names
    cols = {r["name"] for r in db.query("PRAGMA table_info(marking_runs)")}
    assert {"submission_id", "final_marks_json"} <= cols
    assert "submission_id" in {r["name"] for r in db.query("PRAGMA table_info(teacher_queue)")}
    assert "criterion_scores_json" in {r["name"] for r in db.query("PRAGMA table_info(teacher_corrections)")}
