"""Candidate chat endpoints (P5): start → message* (+ nudge on silence).

Each turn runs in ONE transaction holding the conversation's row lock (ADR-024):
lock → read history + data → run the agent → save. If anything fails before the
save, Postgres rolls it all back and the front simply retries.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

import openai
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from prompts import GREETING
from runner import run_nudge, run_turn

router = APIRouter(prefix="/api/chat")

_MAX_NUDGES = 3  # per silence; a candidate message resets the count (ADR-026)


class MessageBody(BaseModel):
    conversation_id: UUID
    message: str = Field(min_length=1, max_length=2000)


class NudgeBody(BaseModel):
    conversation_id: UUID


@contextmanager
def _turn(cid: UUID, *, create: bool = False) -> Iterator[tuple]:
    """The open transaction + the locked conversation row, with the contract's errors."""
    with db.pool().connection() as conn:
        if create:
            db.ensure_conversation(conn, cid, GREETING)
        try:
            conv = db.lock_conversation(conn, cid)
        except db.Busy:
            raise HTTPException(409, "conversation busy, retry") from None
        if conv is None:
            raise HTTPException(404, "conversation not found")
        try:
            yield conn, conv
        except openai.OpenAIError as e:
            raise HTTPException(502, "Rita is unavailable, retry") from e


@router.post("/start")
def start() -> dict:
    # Nothing is stored yet: the first message creates the conversation.
    return {"conversation_id": str(uuid4()), "greeting": GREETING}


@router.post("/message")
def message(body: MessageBody) -> dict:
    with _turn(body.conversation_id, create=True) as (conn, conv):
        history = [*db.get_history(conn, conv["id"]), {"role": "user", "content": body.message}]
        result = run_turn(history, conv["extracted_fields"])
        db.save_turn(conn, conv["id"], body.message, result)
    return {"reply": result.reply, "completed": result.completed, "status": result.status}


@router.post("/nudge")
def nudge(body: NudgeBody) -> dict:
    with _turn(body.conversation_id) as (conn, conv):
        if conv["completed"] or conv["nudge_count"] >= _MAX_NUDGES:
            return {"reply": None}
        reply = run_nudge(db.get_history(conn, conv["id"]), conv["nudge_count"] + 1)
        db.save_nudge(conn, conv["id"], reply)
    return {"reply": reply}
