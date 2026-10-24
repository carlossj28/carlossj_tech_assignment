"""FAQ light RAG (ADR-031): the catalog, the ranking and how chat and voice reach it.

Embeddings are faked with a bag of words, so ranking is checked offline: the
real model only changes how good the neighbours are, not the plumbing.
"""
import os
import re
import zlib

import openai
import pytest

os.environ.setdefault("SESSION_SECRET", "test-secret")

from agent import faq  # noqa: E402
from agent.prompts import SYSTEM_PROMPT  # noqa: E402
from agent.tools import OPENAI_TOOL_SCHEMAS, dispatch  # noqa: E402


def _bag_of_words(texts):
    vectors = []
    for text in texts:
        v = [0.0] * 256
        for word in re.findall(r"\w+", text.lower()):
            v[zlib.crc32(word.encode()) % 256] += 1
        vectors.append(v)
    return vectors


@pytest.fixture
def fake_embed(monkeypatch):
    faq._index.cache_clear()
    monkeypatch.setattr(faq, "_embed", _bag_of_words)
    yield
    faq._index.cache_clear()


def test_catalog_is_small_well_formed_and_unique():
    items = faq.entries()
    assert 10 <= len(items) <= 30  # light RAG on purpose; past hundreds → pgvector
    assert all(set(e) == {"q", "a"} and e["q"].strip() and e["a"].strip() for e in items)
    assert len({e["q"] for e in items}) == len(items)


def test_search_returns_closest_entries_best_first(fake_embed):
    r = faq.search("¿cuál es el sueldo?")
    assert r["ok"] and len(r["results"]) == 3
    assert "sueldo" in r["results"][0]["q"]


def test_faq_outage_returns_no_results_instead_of_failing(monkeypatch):
    faq._index.cache_clear()
    monkeypatch.setattr(faq, "_embed", lambda texts: (_ for _ in ()).throw(openai.OpenAIError("down")))
    assert faq.search("sueldo") == {"ok": True, "results": []}


def test_tool_is_registered_validated_and_leaves_data_alone(fake_embed):
    assert "search_faq" in {t["function"]["name"] for t in OPENAI_TOOL_SCHEMAS}
    extracted = {"full_name": "Ana"}
    assert dispatch("search_faq", extracted, {"query": "turnos"})["results"]
    assert extracted == {"full_name": "Ana"}
    assert "validation_error" in dispatch("search_faq", {}, {"query": ""})


def test_prompt_tells_rita_to_answer_only_from_the_faq():
    assert "search_faq" in SYSTEM_PROMPT and "no inventes" in SYSTEM_PROMPT


def test_voice_faq_lookup_needs_no_database(fake_embed, monkeypatch):
    from fastapi.testclient import TestClient

    import main
    from storage import db
    monkeypatch.setattr(db, "pool", lambda: (_ for _ in ()).throw(AssertionError("no DB on FAQ")))
    body = TestClient(main.app).post("/api/voice/tool", json={
        "conversation_id": "00000000-0000-0000-0000-000000000001",
        "name": "search_faq", "args": {"query": "¿necesito experiencia?"}}).json()
    assert "experiencia" in body["results"][0]["q"]


def test_chat_turn_answers_from_the_faq(fake_embed):
    from test_runner import FakeClient, _completion, _tool_call

    from agent.runner import run_turn
    client = FakeClient([
        _completion(tools=[_tool_call("search_faq", {"query": "sueldo"})]),
        _completion(text="Depende de la ciudad y la jornada. ¿Tienes carné de conducir?"),
    ])
    r = run_turn([{"role": "user", "content": "¿cuánto se cobra?"}], {}, client=client)
    assert r.tool_calls[0]["name"] == "search_faq" and r.tool_calls[0]["result"]["results"]
    assert r.status == "pending" and not r.completed
