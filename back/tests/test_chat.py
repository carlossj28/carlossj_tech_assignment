"""P5 chat endpoints against a real Postgres and a fake OpenAI. Skipped without DATABASE_URL.

Run locally:  docker compose up -d
              DATABASE_URL=postgresql://sazon:sazon@localhost:5432/sazon uv run pytest tests/test_chat.py -v
"""
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import openai
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="needs Postgres (docker compose up -d)"
)


def _completion(text=None, tools=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=tools))])


def _tool(name, args):
    return SimpleNamespace(id=f"c_{name}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class FakeOpenAI:
    """Replays scripted completions; an exception in the script is raised instead."""
    def __init__(self):
        self.script, self.calls = [], []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw["messages"])
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@pytest.fixture
def fake(monkeypatch):
    import runner
    client = FakeOpenAI()
    monkeypatch.setattr(runner, "_default_client", lambda: client)
    return client


@pytest.fixture(scope="module")
def api():
    import db
    from fastapi.testclient import TestClient

    from main import app
    db.init_db()
    return TestClient(app)


def _start(api):
    return api.post("/api/chat/start").json()["conversation_id"]


def _say(api, cid, text):
    return api.post("/api/chat/message", json={"conversation_id": cid, "message": text})


def _turns(cid):
    import db
    return db.get_turns(cid)


def test_start_stores_the_greeting(api):
    body = api.post("/api/chat/start").json()
    assert "Rita" in body["greeting"]
    assert [(t["role"], t["content"]) for t in _turns(body["conversation_id"])] == [
        ("assistant", body["greeting"])]


def test_message_saves_turns_data_and_status(api, fake):
    import db
    cid = _start(api)
    fake.script = [_completion(tools=[_tool("save_answer", {"full_name": "Marta", "has_driver_license": True})]),
                   _completion(text="¿En qué ciudad vives?")]
    r = _say(api, cid, "Soy Marta y tengo carné")
    assert r.status_code == 200
    assert r.json() == {"reply": "¿En qué ciudad vives?", "completed": False, "status": "pending"}

    turns = _turns(cid)
    assert [t["role"] for t in turns] == ["assistant", "user", "assistant"]
    assert turns[2]["tool_calls"][0]["name"] == "save_answer"          # audit trail
    conv = db.get_conversation(cid)
    assert conv["extracted_fields"] == {"full_name": "Marta", "has_driver_license": True}
    assert conv["candidate_name"] == "Marta"


def test_second_turn_sees_text_history_and_saved_data(api, fake):
    cid = _start(api)
    fake.script = [_completion(tools=[_tool("save_answer", {"full_name": "Ana"})]),
                   _completion(text="¿Tienes carné?"), _completion(text="¿Ciudad?")]
    _say(api, cid, "Ana")
    _say(api, cid, "sí")
    messages = fake.calls[-1]
    assert '"full_name": "Ana"' in messages[1]["content"]                 # the saved-data line
    assert all(m["role"] != "tool" and "tool_calls" not in m for m in messages)
    assert [m["content"] for m in messages if m["role"] == "user"] == ["Ana", "sí"]


def test_busy_conversation_returns_409(api, fake):
    import db
    cid = _start(api)
    with db.pool().connection() as holder:
        db.lock_conversation(holder, cid)                    # another turn in flight
        assert _say(api, cid, "hola").status_code == 409


def test_openai_failure_returns_502_and_saves_nothing(api, fake):
    import db
    cid = _start(api)
    fake.script = [_completion(tools=[_tool("save_answer", {"full_name": "Luis"})]),
                   openai.OpenAIError("down")]
    r = _say(api, cid, "Luis")
    assert r.status_code == 502 and "detail" in r.json()
    assert len(_turns(cid)) == 1                               # only the greeting
    assert db.get_conversation(cid)["extracted_fields"] == {}


def test_unknown_or_malformed_id(api):
    assert _say(api, str(uuid4()), "hola").status_code == 404
    assert _say(api, "not-a-uuid", "hola").status_code == 422


def test_three_nudges_per_silence(api, fake):
    cid = _start(api)
    nudge = lambda: api.post("/api/chat/nudge", json={"conversation_id": cid}).json()["reply"]  # noqa: E731
    fake.script = [_completion(text=f"¿Sigues ahí? {i}") for i in range(3)]
    assert [nudge() for _ in range(4)] == ["¿Sigues ahí? 0", "¿Sigues ahí? 1", "¿Sigues ahí? 2", None]

    fake.script = [_completion(text="¿Tu nombre?"), _completion(text="¿Sigues ahí?")]
    _say(api, cid, "perdona, aquí estoy")                      # resets the count
    assert nudge() == "¿Sigues ahí?"


def test_no_nudge_once_completed(api, fake):
    cid = _start(api)
    fake.script = [_completion(tools=[_tool("save_answer", {"has_driver_license": False}),
                                      _tool("end_interview", {"summary": "Sin carné."})]),
                   _completion(text="Gracias, sin carné no podemos seguir.")]
    assert _say(api, cid, "no tengo carné").json()["completed"] is True
    assert api.post("/api/chat/nudge", json={"conversation_id": cid}).json() == {"reply": None}


def test_message_after_close_reopens_and_requalifies(api, fake):
    import db
    cid = _start(api)
    fake.script = [_completion(tools=[_tool("save_answer", {"has_driver_license": True, "city": "Lerín"}),
                                      _tool("end_interview", {"summary": "Fuera de zona."})]),
                   _completion(text="En Lerín no estamos; si te equivocaste, dímelo.")]
    assert _say(api, cid, "tengo carné, vivo en Lerín").json() == {
        "reply": "En Lerín no estamos; si te equivocaste, dímelo.", "completed": True,
        "status": "disqualified"}
    assert db.get_conversation(cid)["knockout_reason"] == "out_of_service_area"

    fake.script = [_completion(tools=[_tool("save_answer", {"city": "Madrid"})]),
                   _completion(text="¡Genial! ¿Qué disponibilidad tienes?")]
    assert _say(api, cid, "perdona, es Madrid").json() == {
        "reply": "¡Genial! ¿Qué disponibilidad tienes?", "completed": False, "status": "qualified"}
    conv = db.get_conversation(cid)
    assert conv["knockout_reason"] is None and conv["summary"] == "Fuera de zona."
