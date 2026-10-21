"""Lightweight guardrails. The heavy lifting is in the system prompt (strict
scope); these are a cheap belt-and-braces layer on top.

Input:  block obvious abuse / prompt-injection before spending a model call.
Output: redact phone-number-like patterns the agent shouldn't emit anyway.

ponytail: regex, not a moderation pipeline. Enough for the demo; swap in a real
moderation API (e.g. OpenAI Moderation) when liability matters.
"""
from __future__ import annotations

import re

_ABUSE = re.compile(r"\b(idiota|est[úu]pid[oa]|gilipollas|puta|fuck|shit|stupid bot)\b", re.IGNORECASE)
_INJECTION = re.compile(
    r"(ignora (?:las|todas)|olvida (?:las|tus)|act[úu]a como|you are now|ignore (?:all|previous)|system prompt)",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?:\+?\d[\s-]?){7,}")

# Short, scope-reconducting replies when input is blocked (ES default / EN).
_REFUSAL = {
    "es": "Vamos a seguir con el proceso de selección. ¿Continuamos?",
    "en": "Let's keep to the screening. Shall we continue?",
}


def is_blocked(message: str) -> bool:
    return bool(_ABUSE.search(message) or _INJECTION.search(message))


def refusal(lang: str) -> str:
    return _REFUSAL.get(lang, _REFUSAL["es"])


def sanitize_output(text: str) -> str:
    """Strip phone-number-like runs from the agent's reply."""
    return _PHONE.sub("[oculto]", text)
