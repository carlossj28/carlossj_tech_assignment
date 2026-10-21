"""Per-turn language detection (ES/EN) for the language-override.

Why override: told only once in the system prompt, the model over-anchors on
the language the chat started in and ignores a mid-conversation switch. So each
turn we detect the candidate's language and pin the reply to it.

ponytail: stop-word heuristic, not a detection library. Screening answers are
short and the choice is binary (ES default); this is enough. Default ES on ties.
"""
from __future__ import annotations

import re

_EN = {"the", "i", "yes", "no", "have", "my", "can", "we", "english", "hi", "hello",
       "license", "driver", "work", "available", "morning", "afternoon", "evening"}
_ES = {"el", "la", "sí", "no", "tengo", "mi", "puedo", "hola", "carné", "carnet",
       "conducir", "trabajo", "mañana", "tarde", "noche", "disponible", "español"}


def detect(text: str) -> str:
    """'en' or 'es' for a single message. Ties and empties default to 'es'."""
    words = set(re.findall(r"[a-záéíóúñü]+", text.lower()))
    return "en" if len(words & _EN) > len(words & _ES) else "es"


_OVERRIDE = {
    "es": "IDIOMA DEL TURNO: el candidato ha escrito en español. Responde 100% en español.",
    "en": "TURN LANGUAGE: the candidate wrote in English. Reply 100% in English.",
}


def override(lang: str) -> str:
    return _OVERRIDE.get(lang, _OVERRIDE["es"])
