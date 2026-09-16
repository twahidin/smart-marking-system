def test_requires_auth(client):
    assert client.get("/api/classes").status_code == 401


def test_create_list_rename_archive_regenerate(auth):
    r = auth.post("/api/classes", json={"name": "4E2 Mathematics"})
    assert r.status_code == 201
    c = r.json()
    assert c["name"] == "4E2 Mathematics" and len(c["code"]) == 4 and c["student_count"] == 0 and c["open_assignments"] == 0
    assert c["archived_at"] is None
    assert auth.post("/api/classes", json={"name": "  "}).json()["error"]["code"] == "bad_name"
    assert [x["id"] for x in auth.get("/api/classes").json()] == [c["id"]]
    assert auth.get(f"/api/classes/{c['id']}").json()["code"] == c["code"]
    assert auth.get("/api/classes/999").status_code == 404
    assert auth.put(f"/api/classes/{c['id']}", json={"name": "4E2 Maths"}).json()["name"] == "4E2 Maths"
    old = c["code"]
    new = auth.post(f"/api/classes/{c['id']}/regenerate-code").json()["code"]
    assert new != old and len(new) == 4
    archived = auth.post(f"/api/classes/{c['id']}/archive").json()
    assert archived["archived_at"] is not None
    # archived classes list last
    d = auth.post("/api/classes", json={"name": "3N1 Science"}).json()
    assert [x["id"] for x in auth.get("/api/classes").json()] == [d["id"], c["id"]]
    assert auth.post(f"/api/classes/{c['id']}/unarchive").json()["archived_at"] is None
