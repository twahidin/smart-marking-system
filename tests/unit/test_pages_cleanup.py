import json
from datetime import datetime, timedelta, timezone

import pytest

from sms.memory.db import Database
from sms.storage import PageStorage
from sms.web.services.pages_cleanup import delete_submission_pages, effective_delete_pages, sweep_done_submissions


@pytest.fixture
def env(tmp_path):
    db = Database(path=str(tmp_path / "s.db"))
    storage = PageStorage(tmp_path / "data")
    return db, storage


def _submission(db, status="done", assignment_id=None, age_hours=0):
    sid = db.insert("INSERT INTO submissions (label, subject, context, rubric_json, status, assignment_id) "
                    "VALUES ('s', 'math', '', '{\"criterion_defs\": []}', :st, :aid) RETURNING id",
                    {"st": status, "aid": assignment_id})
    if age_hours:
        db.execute("UPDATE submissions SET updated_at = :t WHERE id = :id",
                   {"t": (datetime.now(timezone.utc) - timedelta(hours=age_hours)).strftime("%Y-%m-%d %H:%M:%S"),
                    "id": sid})
    return sid


def _page(db, storage, content, *, submission_id=None, template_id=None, kind="student", index=0):
    digest, rel = storage.put_jpeg(content)
    return db.insert("INSERT INTO pages (submission_id, template_id, kind, page_index, sha256, storage_path, width, height) "
                     "VALUES (:s, :t, :k, :i, :h, :p, 1, 1) RETURNING id",
                     {"s": submission_id, "t": template_id, "k": kind, "i": index, "h": digest, "p": rel}), rel


def _template(db, delete_pages=None):
    return db.insert("INSERT INTO assignment_templates (title, subject, context, rubric_json, delete_pages_after_marking) "
                     "VALUES ('T', 'math', '', '{\"criterion_defs\": []}', :d) RETURNING id", {"d": delete_pages})


def _set_global(db, value: bool):
    db.execute("INSERT INTO settings (id, provider, model, rpm_limit, confidence_threshold, delete_pages_after_marking) "
               "VALUES (1, 'openai', 'm', 0, 0, :d)", {"d": value})


def _deleted(db, page_id):
    return db.query("SELECT deleted_at FROM pages WHERE id = :id", {"id": page_id})[0]["deleted_at"]


# --- effective flag ------------------------------------------------------------------------------

def test_effective_flag_follows_template_then_global(env):
    db, storage = env
    assert effective_delete_pages(db, _submission(db)) is True  # no settings row: default on
    _set_global(db, False)
    assert effective_delete_pages(db, _submission(db)) is False  # quick-mark script: global default
    assert effective_delete_pages(db, _submission(db, assignment_id=_template(db, None))) is False  # NULL: global
    assert effective_delete_pages(db, _submission(db, assignment_id=_template(db, True))) is True
    db.execute("UPDATE settings SET delete_pages_after_marking = 1")
    assert effective_delete_pages(db, _submission(db, assignment_id=_template(db, False))) is False
    # a dangling assignment id falls back to the global default
    assert effective_delete_pages(db, _submission(db, assignment_id=999999)) is True


# --- delete_submission_pages ---------------------------------------------------------------------

def test_deletes_student_pages_and_unlinks_files(env):
    db, storage = env
    sid = _submission(db)
    p1, rel1 = _page(db, storage, b"one", submission_id=sid, index=0)
    p2, rel2 = _page(db, storage, b"two", submission_id=sid, index=1)
    assert delete_submission_pages(db, storage, sid) == 2
    assert _deleted(db, p1) and _deleted(db, p2)
    assert not storage.abs(rel1).exists() and not storage.abs(rel2).exists()
    # rows are kept (the detail still lists them), and a second call has nothing to do
    assert db.query("SELECT COUNT(*) AS c FROM pages WHERE submission_id = :s", {"s": sid})[0]["c"] == 2
    assert delete_submission_pages(db, storage, sid) == 0


def test_shared_file_is_kept_while_another_row_references_it(env):
    db, storage = env
    sid = _submission(db)
    other = _submission(db, status="needs_you")
    tid = _template(db)
    p1, rel = _page(db, storage, b"same", submission_id=sid)
    _page(db, storage, b"same", submission_id=other)          # identical page in another script
    paper, paper_rel = _page(db, storage, b"paper", template_id=tid, kind="paper")
    _page(db, storage, b"paper", submission_id=sid, index=1)  # a student page that duplicates the paper
    assert delete_submission_pages(db, storage, sid) == 2
    assert _deleted(db, p1) and storage.abs(rel).exists()
    assert storage.abs(paper_rel).exists() and _deleted(db, paper) is None
    # once the last reference goes, the file goes too
    assert delete_submission_pages(db, storage, other) == 1
    assert not storage.abs(rel).exists()


def test_only_student_pages_of_that_submission(env):
    db, storage = env
    sid = _submission(db)
    other = _submission(db)
    p_other, rel_other = _page(db, storage, b"other", submission_id=other)
    p_scheme, rel_scheme = _page(db, storage, b"scheme", submission_id=sid, kind="scheme", index=5)
    p_student, rel_student = _page(db, storage, b"student", submission_id=sid)
    assert delete_submission_pages(db, storage, sid) == 1
    assert _deleted(db, p_student) and not storage.abs(rel_student).exists()
    assert _deleted(db, p_other) is None and storage.abs(rel_other).exists()
    assert _deleted(db, p_scheme) is None and storage.abs(rel_scheme).exists()


def test_flag_off_leaves_pages_alone(env):
    db, storage = env
    _set_global(db, False)
    sid = _submission(db)
    p, rel = _page(db, storage, b"keep", submission_id=sid)
    assert delete_submission_pages(db, storage, sid) == 0
    assert _deleted(db, p) is None and storage.abs(rel).exists()
    tid = _template(db, True)
    sid2 = _submission(db, assignment_id=tid)
    p2, rel2 = _page(db, storage, b"go", submission_id=sid2)
    assert delete_submission_pages(db, storage, sid2) == 1
    assert _deleted(db, p2) and not storage.abs(rel2).exists()


def test_missing_file_is_not_an_error(env):
    db, storage = env
    sid = _submission(db)
    p, rel = _page(db, storage, b"gone", submission_id=sid)
    storage.abs(rel).unlink()
    assert delete_submission_pages(db, storage, sid) == 1
    assert _deleted(db, p)


def test_unlink_failure_keeps_the_row_marked(env, monkeypatch):
    """A volume hiccup on unlink is logged, not raised: the row is already marked deleted and the
    nightly sweep only re-checks rows that are not."""
    db, storage = env
    sid = _submission(db)
    p, rel = _page(db, storage, b"stuck", submission_id=sid)
    from pathlib import Path
    real_unlink = Path.unlink

    def boom(self, missing_ok=False):
        if self.name.endswith(".jpg"):
            raise OSError("volume unavailable")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", boom)
    assert delete_submission_pages(db, storage, sid) == 1
    assert _deleted(db, p) and storage.abs(rel).exists()


# --- sweep ----------------------------------------------------------------------------------------

def test_sweep_covers_old_done_submissions_with_pages_left(env):
    db, storage = env
    old_done = _submission(db, age_hours=30)
    recent_done = _submission(db, age_hours=1)
    old_needs_you = _submission(db, status="needs_you", age_hours=30)
    old_off = _submission(db, assignment_id=_template(db, False), age_hours=30)
    old_swept = _submission(db, age_hours=30)
    pages = {sid: _page(db, storage, f"p{sid}".encode(), submission_id=sid)
             for sid in (old_done, recent_done, old_needs_you, old_off, old_swept)}
    assert delete_submission_pages(db, storage, old_swept) == 1
    assert sweep_done_submissions(db, storage, older_than_hours=24) == 1
    assert _deleted(db, pages[old_done][0]) and not storage.abs(pages[old_done][1]).exists()
    for sid in (recent_done, old_needs_you, old_off):
        assert _deleted(db, pages[sid][0]) is None and storage.abs(pages[sid][1]).exists()
    # nothing left to sweep
    assert sweep_done_submissions(db, storage, older_than_hours=24) == 0
    # a shorter window picks up the recent one
    assert sweep_done_submissions(db, storage, older_than_hours=0) == 1
    assert _deleted(db, pages[recent_done][0])
