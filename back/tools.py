"""The four agent tools: OpenAI schemas + pure handlers.

Design: handlers take a plain `extracted` dict (the conversation's field store)
and the raw LLM args. They validate, mutate the dict, and return a small result
the model reacts to. No DB, no network here — persistence wraps these in P5, so
the whole screening logic stays unit-testable offline.

The same schemas register with both chat and the Realtime (voice) session; the
same handlers run for both transports (see propuesta-tecnica §03).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from pydantic import ValidationError

from schemas import CompleteScreeningArgs, DisqualifyArgs, FIELD_NAMES, FlagInvalidArgs, RecordFieldArgs
from service_areas import match_zone

Result = dict[str, Any]

# ── OpenAI function schemas (registered in chat + reshaped for Realtime) ────────

OPENAI_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "record_field",
            "description": "Record one screening field. Server validates it; on "
            "failure the result carries validation_error and you re-ask. "
            "For has_driver_license send exactly 'yes' or 'no'; if the answer is "
            "unclear or contradictory, ask again instead of recording it.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["field", "value", "confidence"],
                "properties": {
                    "field": {"type": "string", "enum": FIELD_NAMES},
                    "value": {"type": "string", "minLength": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_invalid",
            "description": "Log an answer you couldn't extract cleanly, before asking to clarify.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["field", "user_value", "reason"],
                "properties": {
                    "field": {"type": "string"},
                    "user_value": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disqualify",
            "description": "Mark the candidate out. Only no_license or out_of_service_area. "
            "Then give a kind closing message.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reason", "detail"],
                "properties": {
                    "reason": {"type": "string", "enum": ["no_license", "out_of_service_area"]},
                    "detail": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_screening",
            "description": "End with a 2-3 sentence summary for the recruiter. Call once, "
            "after all fields are collected or after a disqualification.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary"],
                "properties": {"summary": {"type": "string"}},
            },
        },
    },
]

# ── Value normalization (the checks the LLM can't do itself) ────────────────────

# The model interprets the candidate ("Sí, desde noviembre") and sends yes/no;
# Python only checks the type. Common spellings of a yes/no token are accepted,
# always as the whole value; anything else is rejected, never guessed.
_LICENSE = {
    "yes": True, "si": True, "sí": True, "true": True, "1": True,
    "no": False, "false": False, "0": False,
}


def _normalize(field: str, raw: str) -> Any | None:
    """Coerce a raw LLM string into a typed value, or None if invalid."""
    v = raw.strip()
    if field == "has_driver_license":
        return _LICENSE.get(v.lower())
    if field == "city":
        return match_zone(v)             # canonical "City / Zone" or None
    if field == "start_date":
        try:                             # LLM normalizes natural dates; we validate ISO + future
            d = date.fromisoformat(v)
        except ValueError:
            return None
        return d.isoformat() if d >= date.today() else None
    return v                             # name, availability, schedule, experience, email: pass through


_ERRORS = {
    "city": "City not in a service area.",
    "start_date": "Start date must be today or later (ISO yyyy-mm-dd).",
    "has_driver_license": "Send exactly yes or no.",
}

# ── Handlers (pure: mutate `extracted`, return a result) ────────────────────────


def record_field(extracted: dict, args: dict) -> Result:
    a = RecordFieldArgs.model_validate(args)
    value = _normalize(a.field, a.value)
    if value is None:
        return {"ok": False, "validation_error": _ERRORS.get(a.field, "Invalid value.")}
    extracted[a.field] = value
    return {"ok": True}


def flag_invalid(extracted: dict, args: dict) -> Result:
    FlagInvalidArgs.model_validate(args)   # validate shape only
    return {"ok": True}


def disqualify(extracted: dict, args: dict) -> Result:
    a = DisqualifyArgs.model_validate(args)
    extracted["_disqualified"] = True
    extracted["_disqualification_reason"] = a.reason
    return {"ok": True}


def complete_screening(extracted: dict, args: dict) -> Result:
    CompleteScreeningArgs.model_validate(args)
    return {"ok": True, "qualified": recompute_qualified(extracted)}


def recompute_qualified(extracted: dict) -> bool:
    """The safety net: Python seals the verdict, the model doesn't (propuesta §05)."""
    if extracted.get("_disqualified"):
        return False
    return extracted.get("has_driver_license") is True and extracted.get("city") is not None


HANDLERS: dict[str, Callable[[dict, dict], Result]] = {
    "record_field": record_field,
    "flag_invalid": flag_invalid,
    "disqualify": disqualify,
    "complete_screening": complete_screening,
}


def dispatch(name: str, extracted: dict, args: dict) -> Result:
    """Run a tool call by name; never raise on bad args (returns an error result)."""
    handler = HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": f"unknown tool {name}"}
    try:
        return handler(extracted, args)
    except ValidationError as e:
        return {"ok": False, "error": e.errors()[0]["msg"]}
