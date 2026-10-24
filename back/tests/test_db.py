"""Postgres round-trip for the turn write path. Skipped unless DATABASE_URL is set.

Run locally:  docker compose up -d
              DATABASE_URL=postgresql://sazon:sazon@localhost:5432/sazon \
                  uv run pytest tests/test_db.py -v
"""
import os

import pytest

from agent.runner import TurnResult

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs Postgres (docker compose up -d)"
)


@pytest.fixture(scope="module")
def _db():
    from storage import db
    db.init_db()
    return db


def test_turn_roundtrip(_db):
    cid = _db.start_conversation("chat", "¡Hola!")
    result = TurnResult(reply="¿En qué ciudad?", extracted={"full_name": "Ana", "has_driver_license": True},
                        tool_calls=[{"name": "save_answer", "args": {}, "result": {"ok": True}}])
    with _db.pool().connection() as conn:
        conv = _db.lock_conversation(conn, cid)
        _db.save_turn(conn, conv["id"], "soy Ana, tengo carné", result)

    conv = _db.get_conversation(cid)                  # the rehydrate read voice relies on
    assert conv["candidate_name"] == "Ana"
    assert conv["extracted_fields"]["has_driver_license"] is True
    with _db.pool().connection() as conn:
        history = _db.get_history(conn, cid)
    assert [t["role"] for t in history] == ["assistant", "user", "assistant"]
    assert _db.get_turns(cid)[2]["tool_calls"][0]["name"] == "save_answer"  # audit kept


def test_lock_is_exclusive(_db):
    cid = _db.start_conversation("chat", "¡Hola!")
    with _db.pool().connection() as holder:
        _db.lock_conversation(holder, cid)
        with _db.pool().connection() as other, pytest.raises(_db.Busy):
            _db.lock_conversation(other, cid)
