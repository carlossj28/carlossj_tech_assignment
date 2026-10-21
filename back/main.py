"""Grupo Sazon screening API. Entry point.

Wires DB init on startup (when DATABASE_URL is set), recruiter auth endpoints,
and /health. Agent and conversation endpoints land in later phases.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel

import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("DATABASE_URL"):
        import db
        db.init_db()
    yield


app = FastAPI(title="Sazon Screening API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Recruiter auth ──────────────────────────────────────────────────────────

class LoginBody(BaseModel):
    username: str
    password: str


@app.post("/api/recruiter/login")
def login(body: LoginBody, response: Response) -> dict[str, str]:
    import db
    recruiter = db.get_recruiter(body.username)
    if not recruiter or not auth.verify_password(recruiter["password_hash"], body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    auth.set_cookie(response, auth.issue_session(body.username))
    return {"username": body.username}


@app.post("/api/recruiter/logout")
def logout(response: Response) -> dict[str, bool]:
    auth.clear_cookie(response)
    return {"ok": True}


@app.get("/api/recruiter/me")
def me(username: str = Depends(auth.require_recruiter)) -> dict[str, str]:
    return {"username": username}
