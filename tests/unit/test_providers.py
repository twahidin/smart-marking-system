from sms.memory.db import Database
from sms.memory.providers import ExemplarCasesProvider, RubricNotesProvider


def test_rubric_notes_provider_injects_active_notes_only(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute(
        "INSERT INTO rubric_notes (subject, note, status) VALUES (?, ?, ?)",
        ("math", "State units in final answers.", "active"),
    )
    db.execute(
        "INSERT INTO rubric_notes (subject, note, status) VALUES (?, ?, ?)",
        ("math", "Draft note not shown.", "draft"),
    )
    provider = RubricNotesProvider(db, subject="math")
    info = provider.get_info()
    assert "State units" in info
    assert "Draft note" not in info


def test_rubric_notes_provider_empty(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    provider = RubricNotesProvider(db, subject="math")
    assert provider.get_info() == ""


def test_exemplar_cases_provider_formats_cases(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    db.execute(
        "INSERT INTO exemplar_cases (subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("math", "quadratic equations", "q1", "x = 3 or x = -2, with steps", 5, 5, "Full method marks", "active"),
    )
    provider = ExemplarCasesProvider(db, subject="math")
    info = provider.get_info()
    assert "quadratic" in info
    assert "5/5" in info
    assert "Full method marks" in info
