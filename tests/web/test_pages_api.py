import io
import json

from PIL import Image

from sms.web.services.pages_cleanup import delete_submission_pages
from tests.web.seed_v2 import seed_v2

RUBRIC = {"criterion_defs": [{"id": "c1", "description": "method", "max_score": 2}]}


def _png(size=(20, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


def _with_key(auth):
    auth.put("/api/settings", json={"provider": "openai", "model": "gpt-5-mini", "api_key": "sk-x",
                                    "rpm_limit": 60, "confidence_threshold": 0})
    return auth


def _create(auth, files=None):
    files = files or [("files", ("p1.png", _png(), "image/png")), ("files", ("p2.png", _png((30, 20)), "image/png"))]
    r = auth.post("/api/submissions", data={"label": "Tan", "subject": "math", "context": "", "rubric": json.dumps(RUBRIC)},
                  files=files)
    assert r.status_code == 202
    return r.json()


def test_deleted_page_is_410_gone(auth, app):
    body = _create(_with_key(auth))
    sid, pids = body["id"], [p["id"] for p in body["pages"]]
    assert auth.get(f"/api/pages/{pids[0]}").status_code == 200
    app.state.db.execute("UPDATE submissions SET status = 'done' WHERE id = :s", {"s": sid})
    assert delete_submission_pages(app.state.db, app.state.storage, sid) == 2
    r = auth.get(f"/api/pages/{pids[0]}")
    assert r.status_code == 410
    assert r.json() == {"error": {"code": "gone", "message": "Page deleted after marking"}}
    assert auth.get(f"/api/pages/{pids[1]}").status_code == 410
    assert auth.get("/api/pages/999999").status_code == 404


def test_paper_pages_are_unaffected_by_deletion(auth, app):
    auth = _with_key(auth)
    t = auth.post("/api/assignments", json={"title": "W", "subject": "math", "context": "", "rubric": RUBRIC}).json()
    r = auth.post(f"/api/assignments/{t['id']}/paper", files=[("files", ("paper.png", _png(), "image/png"))])
    assert r.status_code == 200, r.text
    paper_pid = r.json()["pages"][0]["id"]
    # a script whose page is the very same image as the paper (content-addressed: one file on disk)
    body = _create(auth, files=[("files", ("p1.png", _png(), "image/png"))])
    app.state.db.execute("UPDATE submissions SET status = 'done' WHERE id = :s", {"s": body["id"]})
    assert delete_submission_pages(app.state.db, app.state.storage, body["id"]) == 1
    assert auth.get(f"/api/pages/{body['pages'][0]['id']}").status_code == 410
    assert auth.get(f"/api/pages/{paper_pid}").status_code == 200


def test_detail_marks_deleted_pages(auth, app):
    body = _create(_with_key(auth))
    sid = body["id"]
    d = auth.get(f"/api/submissions/{sid}").json()
    assert [p["deleted"] for p in d["pages"]] == [False, False] and d["pages_deleted"] is False
    db = app.state.db
    db.execute("UPDATE submissions SET status = 'done' WHERE id = :s", {"s": sid})
    delete_submission_pages(db, app.state.storage, sid)
    d = auth.get(f"/api/submissions/{sid}").json()
    assert len(d["pages"]) == 2 and all(p["deleted"] for p in d["pages"]) and d["pages_deleted"] is True
    assert d["pages"][0]["id"] == body["pages"][0]["id"] and d["pages"][0]["width"] == 20
    # partially deleted (an interrupted earlier run): listed, but not "pages deleted"
    db.execute("UPDATE pages SET deleted_at = NULL WHERE id = :id", {"id": body["pages"][1]["id"]})
    d = auth.get(f"/api/submissions/{sid}").json()
    assert [p["deleted"] for p in d["pages"]] == [True, False] and d["pages_deleted"] is False
    # the list keeps its page count
    assert auth.get("/api/submissions").json()[0]["page_count"] == 2


def test_queue_items_skip_deleted_page_ids(auth, app):
    sid, qids = seed_v2(app)
    db = app.state.db
    db.execute("INSERT INTO pages (submission_id, page_index, sha256, storage_path, width, height) "
               "VALUES (:s, 1, 'h2', 'pages/h2.jpg', 1, 1)", {"s": sid})
    items = auth.get("/api/queue").json()
    assert len(items[0]["page_ids"]) == 2
    kept = items[0]["page_ids"][1]
    db.execute("UPDATE pages SET deleted_at = CURRENT_TIMESTAMP WHERE submission_id = :s AND page_index = 0", {"s": sid})
    assert auth.get("/api/queue").json()[0]["page_ids"] == [kept]
