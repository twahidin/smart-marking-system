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
