"""Answer crops on the API: crop_id on parts and queue items, the image route, deletion with the hand-in."""
from tests.web.seed_v2 import seed_v2


def _crop(app, sid, q_id, content=b"\xff\xd8\xff\xe0JPEGBYTES\xff\xd9"):
    db, storage = app.state.db, app.state.storage
    digest, rel = storage.put_crop(content)
    return db.insert("INSERT INTO part_crops (submission_id, q_id, page_index, storage_path, sha256, width, height) "
                     "VALUES (:s, :q, 0, :p, :h, 10, 10) RETURNING id", {"s": sid, "q": q_id, "p": rel, "h": digest})


def test_parts_carry_their_crop_and_the_route_serves_it(app, auth):
    sid, _ = seed_v2(app)
    cid = _crop(app, sid, "1a")
    parts = {p["q_id"]: p for p in auth.get(f"/api/submissions/{sid}").json()["parts"]}
    assert parts["1a"]["crop_id"] == cid and parts["1b"]["crop_id"] is None
    r = auth.get(f"/api/crops/{cid}")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/jpeg") and r.content.startswith(b"\xff\xd8")
    assert auth.get("/api/crops/999999").status_code == 404


def test_crop_route_needs_a_teacher(app, client):
    sid, _ = seed_v2(app)
    cid = _crop(app, sid, "1a")
    assert client.get(f"/api/crops/{cid}").status_code == 401


def test_queue_items_carry_the_crop(app, auth):
    sid, items = seed_v2(app, queue={"2": "not in scheme"})
    cid = _crop(app, sid, "2")
    item = next(i for i in auth.get("/api/queue").json() if i["submission_id"] == sid)
    assert item["crop_id"] == cid


def test_deleted_crop_is_gone_from_parts_and_route(app, auth):
    sid, _ = seed_v2(app)
    cid = _crop(app, sid, "1a")
    app.state.db.execute("UPDATE part_crops SET deleted_at = CURRENT_TIMESTAMP WHERE id = :c", {"c": cid})
    parts = {p["q_id"]: p for p in auth.get(f"/api/submissions/{sid}").json()["parts"]}
    assert parts["1a"]["crop_id"] is None and auth.get(f"/api/crops/{cid}").status_code == 404
