import json

from sms.cli import build_parser, main


def test_cli_mark_invokes_pipeline(tmp_path, monkeypatch):
    class FakePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, images, assignment_context, rubric):
            class R:
                run_id = "abc123"
                escalations = []

                class F:
                    summary = "ok"
                    def model_dump(self):
                        return {"summary": "ok"}

                feedback = F()

                class M:
                    marks = []
                final_marks = M()
            return R()

    import sms.cli as cli_mod
    monkeypatch.setattr(cli_mod, "MarkingPipeline", FakePipeline)

    rubric_file = tmp_path / "rubric.json"
    rubric_file.write_text(json.dumps({
        "criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]
    }))
    img = tmp_path / "script.png"
    img.write_bytes(b"png")

    exit_code = main([
        "mark", str(img),
        "--subject", "math",
        "--rubric", str(rubric_file),
        "--db", str(tmp_path / "sms.db"),
    ])
    assert exit_code == 0


def test_cli_queue_lists_pending(tmp_path, capsys):
    db_path = str(tmp_path / "sms.db")
    from sms.memory.db import Database
    db = Database(path=db_path)
    db.execute("INSERT INTO teacher_queue (run_id, q_id, reason) VALUES ('r1', 'q1', 'escalated')")

    exit_code = main(["queue", "list", "--db", db_path])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "r1" in out and "q1" in out


def test_cli_notes_roundtrip(tmp_path, capsys):
    db_path = str(tmp_path / "sms.db")
    from sms.memory.db import Database
    db = Database(path=db_path)
    db.execute("INSERT INTO rubric_notes (subject, note, status) VALUES ('math', 'note text', 'draft')")

    assert main(["notes", "list", "--db", db_path]) == 0
    assert "note text" in capsys.readouterr().out

    assert main(["notes", "approve", "1", "--db", db_path]) == 0
    row = db.query("SELECT status FROM rubric_notes WHERE id = 1")[0]
    assert row["status"] == "active"


def test_cli_queue_resolve_records_agent_mark(tmp_path, capsys):
    db_path = str(tmp_path / "sms.db")
    import json as jsonlib

    from sms.memory.db import Database
    db = Database(path=db_path)
    db.execute(
        "INSERT INTO marking_runs (run_id, stage, subject, rubric_json, marks_json, final_status) "
        "VALUES ('r1', 'complete', 'math', '{}', ?, 'escalated')",
        (jsonlib.dumps({"marks": [{"q_id": "q1", "criterion_scores": [2], "total": 2,
                                   "confidence": 0.7, "rationale": "r", "evidence": "e"}]}),),
    )
    db.execute("INSERT INTO teacher_queue (run_id, q_id, reason) VALUES ('r1', 'q1', 'escalated')")

    exit_code = main(["queue", "resolve", "1", "--teacher-mark", "3", "--db", db_path])
    assert exit_code == 0
    corr = db.query("SELECT agent_mark, teacher_mark FROM teacher_corrections")[0]
    assert corr["agent_mark"] == 2
    assert corr["teacher_mark"] == 3

    assert main(["queue", "resolve", "1", "--teacher-mark", "3", "--db", db_path]) == 1


def test_cli_exemplars_roundtrip(tmp_path, capsys):
    db_path = str(tmp_path / "sms.db")
    from sms.memory.db import Database
    db = Database(path=db_path)
    db.execute(
        "INSERT INTO exemplar_cases (subject, topic, q_id, answer_text, awarded, max_score, why_it_matters, status) "
        "VALUES ('math', 'algebra', 'q1', 'x = 3 (cm)', 5, 5, 'units stated', 'draft')"
    )

    assert main(["exemplars", "list", "--db", db_path]) == 0
    assert "algebra" in capsys.readouterr().out

    assert main(["exemplars", "approve", "1", "--db", db_path]) == 0
    row = db.query("SELECT status FROM exemplar_cases WHERE id = 1")[0]
    assert row["status"] == "active"


def test_cli_mark_passes_confidence_threshold(tmp_path, monkeypatch):
    class FakePipeline:
        def __init__(self, *args, **kwargs):
            FakePipeline.kwargs = kwargs

        def run(self, images, assignment_context, rubric):
            class R:
                run_id = "abc"
                escalations = []

                class F:
                    summary = "ok"
                    def model_dump(self): return {"summary": "ok"}
                feedback = F()

                class M:
                    marks = []
                final_marks = M()
            return R()

    import sms.cli as cli_mod
    monkeypatch.setattr(cli_mod, "MarkingPipeline", FakePipeline)

    rubric_file = tmp_path / "rubric.json"
    rubric_file.write_text('{"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]}')
    img = tmp_path / "script.png"
    img.write_bytes(b"png")

    exit_code = main([
        "mark", str(img), "--subject", "math", "--rubric", str(rubric_file),
        "--db", str(tmp_path / "sms.db"), "--confidence-threshold", "0.6",
    ])
    assert exit_code == 0
    assert FakePipeline.kwargs.get("confidence_threshold") == 0.6
