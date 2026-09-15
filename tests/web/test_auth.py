def test_login_sets_cookie_and_me_works(client):
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/login", json={"password": "letmein"})
    assert r.status_code == 204 and "sms_session" in r.cookies
    assert client.get("/api/auth/me").json() == {"authenticated": True}


def test_wrong_password_401_with_error_shape(client):
    r = client.post("/api/auth/login", json={"password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "bad_password"


def test_logout_clears(auth):
    auth.post("/api/auth/logout")
    assert auth.get("/api/auth/me").status_code == 401


def test_login_rate_limited_after_five_failures(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "nope"})
    r = client.post("/api/auth/login", json={"password": "nope"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"


def test_tampered_cookie_rejected(client):
    client.cookies.set("sms_session", "garbage")
    assert client.get("/api/auth/me").status_code == 401
