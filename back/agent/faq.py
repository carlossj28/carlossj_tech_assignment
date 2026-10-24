"""Candidate FAQ: light RAG over a JSON file, embeddings kept in memory (ADR-031).

Rita calls the search_faq tool with the candidate's doubt; we embed it, rank the
FAQ entries by cosine similarity and return the closest few. Only those reach the
model, so it answers from the company's text instead of improvising.

Why no vector DB: ~20 entries fit in memory and rank in microseconds. The FAQ is
embedded once, on the first search, and cached for the process. At thousands of
entries the ranking moves to Postgres (pgvector) and `search`'s signature stays.

If embedding fails, the search returns no results and Rita refers the doubt to the
recruiting team: a FAQ outage must never break the interview.
"""
from __future__ import annotations

import json
import logging
import math
import os
from functools import lru_cache
from pathlib import Path

import openai

_DATA = Path(__file__).resolve().parent / "data" / "faq.demo.v1.json"
_TOP_K = 3
log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def entries() -> list[dict[str, str]]:
    return json.loads(_DATA.read_text("utf-8"))


@lru_cache(maxsize=1)
def _client():
    return openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _embed(texts: list[str]) -> list[list[float]]:
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    return [d.embedding for d in _client().embeddings.create(model=model, input=texts).data]


@lru_cache(maxsize=1)
def _index() -> list[list[float]]:
    """One vector per entry (question + answer), computed once per process."""
    return _embed([f"{e['q']} {e['a']}" for e in entries()])


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def search(query: str) -> dict:
    """The closest FAQ entries to the candidate's doubt, best first."""
    try:
        index, (q,) = _index(), _embed([query])
    except openai.OpenAIError:
        log.exception("FAQ search failed; Rita refers the doubt to the team")
        return {"ok": True, "results": []}
    ranked = sorted(zip(index, entries()), key=lambda p: _cosine(q, p[0]), reverse=True)
    return {"ok": True, "results": [e for _, e in ranked[:_TOP_K]]}
