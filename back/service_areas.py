"""City/zone matching against the service-area catalog.

RapidFuzz over stdlib difflib: in a hiring flow a missed city match = a wrongly
rejected candidate, so match *quality* beats saving a dependency. WRatio handles
the cases difflib's subsequence match misses — partial input ("vivo en el centro
de Madrid") and transposed typos ("Madird"→"Madrid").

Scaling note: this scales by *calls* (stateless API replicas), not catalog size.
For thousands of zones, add a prefilter/index (e.g. Postgres pg_trgm) ahead of
the scorer — `match_zone`'s signature stays put, so callers never change.
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
    """Strip accents + lowercase, so 'cuauhtemoc' matches 'Cuauhtémoc'."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


@lru_cache(maxsize=1)
def _zones() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(canonical labels, normalized labels) paired by index. Loaded once."""
    catalog: dict[str, list[str]] = json.loads(_DATA.read_text("utf-8"))
    labels = tuple(f"{city} / {zone}" for city, zones in catalog.items() for zone in zones)
    return labels, tuple(_norm(label) for label in labels)


def match_zone(text: str) -> str | None:
    """Best canonical "City / Zone" for free-text input, or None below threshold."""
    if not text.strip():
        return None
    labels, normed = _zones()
    best = process.extractOne(_norm(text), normed, scorer=fuzz.WRatio)
    if best and best[1] >= _THRESHOLD:
        return labels[best[2]]  # best = (match, score, index)
    return None
