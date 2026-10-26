"""Per-turn language detection (ES/EN) for the language-override.

Why override: told only once in the system prompt, the model over-anchors on
the language the chat started in and ignores a mid-conversation switch. So each
turn we detect the candidate's language and pin the reply to it.

ponytail: stop-word heuristic, not a detection library. Screening answers are
short and the choice is binary (ES default); this is enough. On a tie ("Full time")
the conversation keeps the language it was in.
"""
from __future__ import annotations

import re

_EN = {"the", "i", "yes", "no", "have", "my", "can", "we", "english", "hi", "hello",
       "license", "driver", "work", "available", "morning", "afternoon", "evening",
       "you", "your", "what", "which", "are", "is", "thanks", "great", "full", "time",
       "part", "weekends", "years", "start", "next", "month"}
_ES = {"el", "la", "sí", "no", "tengo", "mi", "puedo", "hola", "carné", "carnet",
       "conducir", "trabajo", "mañana", "tarde", "noche", "disponible", "español"}


def detect(text: str, tie: str = "es") -> str:
    """'en' or 'es' for a single message; `tie` on ties and empties."""
    words = set(re.findall(r"[a-záéíóúñü]+", text.lower()))
    en, es = len(words & _EN), len(words & _ES)
    return "en" if en > es else "es" if es > en else tie


def conversation_lang(history: list[dict]) -> str:
    """The candidate's current language: their last message, or the one before on a tie."""
    lang = "es"
    for m in history:
        if m["role"] == "user":
            lang = detect(m["content"], tie=lang)
    return lang


_OVERRIDE = {
    "es": "IDIOMA DEL TURNO: el candidato ha escrito en español. Responde 100% en español.",
    "en": "TURN LANGUAGE: the candidate wrote in English. Reply 100% in English.",
}


def override(lang: str) -> str:
    return _OVERRIDE.get(lang, _OVERRIDE["es"])
