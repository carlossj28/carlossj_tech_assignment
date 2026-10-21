"""P3 auth checks: password hashing, signed-cookie lifecycle, login endpoint."""
import os

os.environ.setdefault("SESSION_SECRET", "test-secret")

import auth  # noqa: E402


def test_password_hash_roundtrip():
    h = auth.hash_password("correct horse")
    assert auth.verify_password(h, "correct horse")
    assert not auth.verify_password(h, "wrong")


def test_session_cookie_valid_and_tampered():
    token = auth.issue_session("demo")
    assert auth.read_session(token) == "demo"
    assert auth.read_session(None) is None
    assert auth.read_session(token + "x") is None        # tampered signature


def test_session_expired(monkeypatch):
    token = auth.issue_session("demo")
    monkeypatch.setattr(auth, "_MAX_AGE", -1)             # force expiry
    assert auth.read_session(token) is None


def test_login_flow(monkeypatch):
    """Login with a stubbed DB: good creds set a cookie, bad creds 401."""
    from fastapi.testclient import TestClient
    import db
    import main

    stored = auth.hash_password("s3cret")
    monkeypatch.setattr(db, "get_recruiter", lambda u: {"username": u, "password_hash": stored} if u == "demo" else None)
    client = TestClient(main.app)

    assert client.post("/api/recruiter/login", json={"username": "demo", "password": "nope"}).status_code == 401
    assert client.get("/api/recruiter/me").status_code == 401  # no cookie yet

    ok = client.post("/api/recruiter/login", json={"username": "demo", "password": "s3cret"})
    assert ok.status_code == 200 and ok.json() == {"username": "demo"}
    assert client.get("/api/recruiter/me").json() == {"username": "demo"}  # cookie carried by client
