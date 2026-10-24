"""Recruiter panel endpoints: every conversation and its detail, behind the login.

The front filters by status itself; no server-side filters or paging yet (a
door to open when the list grows past what one page can show).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api import auth
from storage import db

router = APIRouter(prefix="/api/recruiter", dependencies=[Depends(auth.require_recruiter)])

_INACTIVE_AFTER_MIN = 5  # open and quiet this long → "inactive" (ADR-018)


@router.get("/conversations")
def conversations() -> list[dict]:
    return db.list_conversations(_INACTIVE_AFTER_MIN)


@router.get("/conversations/{cid}")
def conversation(cid: UUID) -> dict:
    conv = db.get_conversation_detail(cid, _INACTIVE_AFTER_MIN)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    turns = [{"role": t["role"], "content": t["content"], "created_at": t["created_at"]}
             for t in db.get_turns(str(cid))]
    return {**conv, "turns": turns}
