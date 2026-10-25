"""Voice: the session key (no DB) and the bridge the browser relays to (needs Postgres)."""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("SESSION_SECRET", "test-secret")

from fastapi.testclient import TestClient  # noqa: E402


def test_session_mints_key_with_same_brain_and_stores_nothing(monkeypatch):
    import main
    from api import voice
    from storage import db

    sent = {}
    fake = SimpleNamespace(realtime=SimpleNamespace(client_secrets=SimpleNamespace(
        create=lambda session: sent.update(session) or SimpleNamespace(value="ek_test"))))
    monkeypatch.setattr(voice, "_default_client", lambda: fake)
    monkeypatch.setattr(db, "pool", lambda: (_ for _ in ()).throw(AssertionError("no DB on session")))

    body = TestClient(main.app).post("/api/voice/session").json()

    assert body["client_secret"] == "ek_test" and len(body["conversation_id"]) == 36
    assert {t["name"] for t in sent["tools"]} == {"save_answer", "end_interview", "find_slots", "book_interview", "search_faq"}
    assert all("function" not in t and t["type"] == "function" for t in sent["tools"])  # Realtime shape
    assert "Eres Rita" in sent["instructions"] and "llamada" in sent["instructions"]
    assert "¿Puedo ayudarte en algo más?" in sent["instructions"]  # asked before hanging up (ADR-029)
    assert "no leas la lista" in sent["instructions"]  # a call doesn't read 12 cities aloud
    assert "«dímelo» en vez de «escríbeme»" in sent["instructions"]  # spoken knock-out, not chat text
    assert "en voz no cierres en ese mismo turno" in sent["instructions"]  # the chat rule closes at once
    assert "asistente virtual" in sent["instructions"]  # says she's an AI, like the chat greeting
    assert "llama a save_answer antes de contestarle" in sent["instructions"]  # saves, not just says so
    assert "problema técnico" in sent["instructions"]  # only voice gets `error` (browser fallback)
    assert sent["audio"]["input"]["transcription"]["model"] == "gpt-transcribe"
    assert sent["audio"]["output"]["voice"] == "marin"
    assert sent["audio"]["input"]["noise_reduction"] == {"type": "near_field"}  # noise doesn't cut Rita off
    assert sent["audio"]["input"]["turn_detection"]["threshold"] > 0.5


# ── Bridge: tool calls + transcript, against a real Postgres ──────────────────

needs_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs Postgres (docker compose up -d)")


@pytest.fixture(scope="module")
def api():
    import main
    from storage import db
    db.init_db()
    return TestClient(main.app)


def _cid(api, monkeypatch):
    from api import voice
    fake = SimpleNamespace(realtime=SimpleNamespace(client_secrets=SimpleNamespace(
        create=lambda session: SimpleNamespace(value="ek"))))
    monkeypatch.setattr(voice, "_default_client", lambda: fake)
    return api.post("/api/voice/session").json()["conversation_id"]


@needs_db
def test_rita_alone_creates_nothing_candidate_does(api, monkeypatch):
    from storage import db
    cid = _cid(api, monkeypatch)
    rita = {"role": "assistant", "text": "¡Hola! Soy Rita. ¿Cómo te llamas?"}
    assert api.post("/api/voice/transcript", json={"conversation_id": cid, "turns": [rita]}).status_code == 404
    assert db.get_conversation(cid) is None                                 # nobody answered: no row

    r = api.post("/api/voice/transcript", json={"conversation_id": cid,
                                                "turns": [rita, {"role": "user", "text": "Soy Marta"}]})
    assert r.status_code == 200
    assert db.get_conversation(cid)["source"] == "voice"
    assert [(t["role"], t["content"]) for t in db.get_turns(cid)] == [
        ("assistant", rita["text"]), ("user", "Soy Marta")]


@needs_db
def test_tool_runs_same_brain_and_closes(api, monkeypatch):
    from storage import db
    cid = _cid(api, monkeypatch)
    tool = lambda name, args: api.post("/api/voice/tool", json={"conversation_id": cid, "name": name, "args": args}).json()  # noqa: E731

    assert tool("save_answer", {"full_name": "Marta", "has_driver_license": True, "city": "Madrid"}) == {
        "ok": True, "status": "qualified"}
    assert tool("save_answer", {"start_date": "2000-01-01"})["ok"] is False   # validation_error → model re-asks
    assert tool("end_interview", {"summary": "Apta, Madrid."})["ok"] is False  # tone missing → re-ask
    assert tool("end_interview", {"summary": "Apta, Madrid.", "sentiment": "positive"})["ok"] is True

    conv = db.get_conversation(cid)
    assert conv["screening_status"] == "qualified" and conv["completed"] is True
    assert conv["summary"] == "Apta, Madrid." and conv["candidate_name"] == "Marta"
    assert conv["sentiment"] == "positive"
