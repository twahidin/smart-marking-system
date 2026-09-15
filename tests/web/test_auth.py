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


def test_login_missing_password_400_validation_shape(client):
    r = client.post("/api/auth/login", json={})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "validation"


def test_login_rate_limit_is_per_forwarded_ip(client):
    for _ in range(5):
        client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": "1.1.1.1"})
    blocked = client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": "1.1.1.1"})
    assert blocked.status_code == 429

    still_allowed = client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": "2.2.2.2"})
    assert still_allowed.status_code == 401
    assert still_allowed.json()["error"]["code"] == "bad_password"


def test_login_rate_limit_uses_rightmost_forwarded_hop(client):
    """The leftmost X-Forwarded-For entry is attacker-supplied; only the rightmost (edge proxy) counts."""
    for i in range(5):
        client.post("/api/auth/login", json={"password": "nope"},
                    headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"})
    # Rotating the leftmost hop again does not help — the edge-observed address is what is limited.
    r = client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": "10.0.0.99, 203.0.113.9"})
    assert r.status_code == 429

    # A different rightmost hop is a genuinely different client.
    r = client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": "10.0.0.99, 198.51.100.7"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_password"


def test_login_global_cap_blocks_spoofed_ip_rotation(client):
    """30 failures spread across 30 spoofed IPs block the 31st attempt, even from a fresh IP."""
    for i in range(30):
        r = client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": f"192.0.2.{i}"})
        assert r.status_code == 401, i
    r = client.post("/api/auth/login", json={"password": "nope"}, headers={"X-Forwarded-For": "192.0.2.200"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"
    # The correct password is also refused while the global cap is tripped.
    r = client.post("/api/auth/login", json={"password": "letmein"}, headers={"X-Forwarded-For": "192.0.2.201"})
    assert r.status_code == 429


def test_login_limiter_global_window_expires(monkeypatch):
    from sms.web.deps import LoginLimiter

    clock = {"t": 1000.0}
    monkeypatch.setattr("sms.web.deps.time.monotonic", lambda: clock["t"])
    lim = LoginLimiter(limit=5, window_s=60.0, global_limit=3)
    for ip in ("a", "b", "c"):
        assert not lim.blocked(ip)
        lim.record_failure(ip)
    assert lim.blocked("d")
    clock["t"] += 61
    assert not lim.blocked("d")


def test_login_password_compare_is_constant_time(client, monkeypatch):
    import sms.web.routers.auth as auth_module

    calls = []
    real = auth_module.secrets.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(auth_module.secrets, "compare_digest", spy)
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert calls == [(b"nope", b"letmein")]
