"""P2 integration: real Postgres round-trip. Skipped unless DATABASE_URL is set.

Run locally:  docker compose up -d
              DATABASE_URL=postgresql://sazon:sazon@localhost:5432/sazon \
                  uv run pytest tests/test_db.py -v
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs Postgres (docker compose up -d)"
)


@pytest.fixture(scope="module")
def _db():
    import db
    db.init_db()
    return db


def test_roundtrip_and_rehydrate(_db):
    cid = _db.start_conversation("chat")
    _db.save_extracted(cid, {"full_name": "Ana", "has_driver_license": True, "city": "Madrid / Centro"})
    _db.append_turn(cid, "user", "soy Ana, tengo carné")

    conv = _db.get_conversation(cid)                 # the rehydrate read voice relies on
    assert conv["candidate_name"] == "Ana"
    assert conv["extracted_fields"]["city"] == "Madrid / Centro"
    assert conv["status"] == "in_progress"
    assert len(_db.get_turns(cid)) == 1


def test_close_is_idempotent_advance_only(_db):
    cid = _db.start_conversation("voice")
    first = _db.close_conversation(
        cid, outcome="qualified", qualified=True, reason=None, closed_by="confirm", summary="ok"
    )
    second = _db.close_conversation(
        cid, outcome="review", qualified=None, reason=None, closed_by="idle", summary="late sweep"
    )
    assert first is True            # first trigger seals
    assert second is False          # late trigger is a no-op
    assert _db.get_conversation(cid)["outcome"] == "qualified"  # not degraded
