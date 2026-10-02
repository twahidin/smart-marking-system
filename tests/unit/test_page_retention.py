"""page_retention: 'crops' keeps answer crops and deletes pages/files; 'pages' keeps everything; 'none' deletes all."""
import pytest

from sms.web.services.pages_cleanup import delete_submission_pages, effective_retention
from tests.unit.test_pages_cleanup import _page, _submission, env  # noqa: F401 - fixture


def _global(db, mode):
    db.execute("INSERT INTO settings (id, provider, model, rpm_limit, confidence_threshold, page_retention) "
               "VALUES (1, 'openai', 'm', 0, 0, :m)", {"m": mode})


def _template(db, mode=None):
    return db.insert("INSERT INTO assignment_templates (title, subject, context, rubric_json, page_retention) "
                     "VALUES ('T', 'math', '', '{\"criterion_defs\": []}', :m) RETURNING id", {"m": mode})


def _crop(db, storage, sid, q_id="1a"):
    digest, rel = storage.put_crop(b"\xff\xd8\xff\xd9")
    cid = db.insert("INSERT INTO part_crops (submission_id, q_id, page_index, storage_path, sha256, width, height) "
                    "VALUES (:s, :q, 0, :p, :h, 10, 10) RETURNING id", {"s": sid, "q": q_id, "p": rel, "h": digest})
    return cid, rel


@pytest.mark.parametrize("mode,pages_left,crops_left", [("crops", 0, 1), ("pages", 1, 1), ("none", 0, 0)])
def test_cleanup_per_retention_mode(env, mode, pages_left, crops_left):
    db, storage = env
    _global(db, mode)
    sid = _submission(db)
    _page(db, storage, b"p", submission_id=sid)
    cid, rel = _crop(db, storage, sid)
    delete_submission_pages(db, storage, sid)
    assert db.query("SELECT COUNT(*) AS c FROM pages WHERE submission_id = :s AND deleted_at IS NULL", {"s": sid})[0]["c"] == pages_left
    row = db.query("SELECT deleted_at FROM part_crops WHERE id = :c", {"c": cid})[0]
    assert (row["deleted_at"] is None) == bool(crops_left)
    assert storage.abs(rel).exists() == bool(crops_left)


def test_assignment_overrides_global_retention(env):
    db, storage = env
    _global(db, "none")
    sid = _submission(db, assignment_id=_template(db))
    assert effective_retention(db, sid) == "none"
    sid2 = _submission(db, assignment_id=_template(db, "pages"))
    assert effective_retention(db, sid2) == "pages"


def test_default_when_nothing_saved_is_crops(env):
    db, storage = env
    assert effective_retention(db, _submission(db)) == "crops"
