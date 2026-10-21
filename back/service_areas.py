"""City matching against the service-area catalog (ADR-020: coverage by city).

The catalog maps each covered city to its aliases ("CDMX" → Ciudad de México).
The same file feeds the matcher and the system prompt, so Rita only offers
cities that really exist in the catalog.

RapidFuzz over stdlib difflib: in a hiring flow a missed city match = a wrongly
rejected candidate, so match *quality* beats saving a dependency. WRatio handles
the cases difflib's subsequence match misses — partial input ("vivo en
Valencia") and transposed typos ("Madird"→"Madrid").

Scaling note: this scales by *calls* (stateless API replicas), not catalog size.
For thousands of cities, add a prefilter/index (e.g. Postgres pg_trgm) ahead of
the scorer — `match_city`'s signature stays put, so callers never change.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

# WRatio threshold. 80 (not 85) so a 1-char transposition on a short name
# passes ("Madird"→"Madrid" scores ~83) while noise stays out ("Atlantis" ~62).
_THRESHOLD = 80
_DATA = Path(__file__).resolve().parent / "data" / "service_areas.demo.v1.json"


def _norm(s: str) -> str:
    """Strip accents + lowercase, so 'queretaro' matches 'Querétaro'."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


@lru_cache(maxsize=1)
def _catalog() -> dict[str, list[str]]:
    return json.loads(_DATA.read_text("utf-8"))


@lru_cache(maxsize=1)
def _names() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(canonical city, normalized name or alias) pairs by index. Loaded once."""
    pairs = [(city, name) for city, aliases in _catalog().items() for name in [city, *aliases]]
    return tuple(c for c, _ in pairs), tuple(_norm(n) for _, n in pairs)


def cities() -> list[str]:
    """Covered cities, in catalog order (for the prompt and the KO message)."""
    return list(_catalog())


def match_city(text: str) -> str | None:
    """Canonical covered city for free-text input, or None below threshold."""
    if not text.strip():
        return None
    canon, normed = _names()
    best = process.extractOne(_norm(text), normed, scorer=fuzz.WRatio)
    if best and best[1] >= _THRESHOLD:
        return canon[best[2]]  # best = (match, score, index)
    return None
