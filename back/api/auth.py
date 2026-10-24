"""Recruiter auth: password hashing, a signed session cookie, and the
`require_recruiter` dependency that gates the dashboard endpoints.

Stateless by design (no sessions table): the cookie carries the username,
signed + expiring via itsdangerous. Swapping to SSO later only touches this
file — endpoints just depend on `require_recruiter` (see ADR-011).
"""
from __future__ import annotations

import os

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_COOKIE = "session"
_MAX_AGE = 8 * 3600  # 8h working session
_hasher = PasswordHasher()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.environ["SESSION_SECRET"], salt="recruiter-session")


# ── Passwords ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hash_: str, password: str) -> bool:
    try:
        return _hasher.verify(hash_, password)
    except VerifyMismatchError:
        return False


# ── Session cookie ──────────────────────────────────────────────────────────

def issue_session(username: str) -> str:
    """Signed token to put in the cookie after a successful login."""
    return _serializer().dumps(username)


def read_session(token: str | None) -> str | None:
    """Username from a valid, unexpired token; None otherwise."""
    if not token:
        return None
    try:
        return _serializer().loads(token, max_age=_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def set_cookie(response, token: str) -> None:
    # secure=True needs HTTPS; off in local/dev over http. COOKIE_SECURE=1 in prod.
    secure = os.getenv("COOKIE_SECURE", "0") == "1"
    response.set_cookie(
        _COOKIE, token, max_age=_MAX_AGE,
        httponly=True, samesite="strict", secure=secure,
    )


def clear_cookie(response) -> None:
    response.delete_cookie(_COOKIE)


# ── Dependency ──────────────────────────────────────────────────────────────

def require_recruiter(session: str | None = Cookie(default=None)) -> str:
    """FastAPI dependency: returns the username or 401. Gate endpoints with it."""
    username = read_session(session)
    if username is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return username
