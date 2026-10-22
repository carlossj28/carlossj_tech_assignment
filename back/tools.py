"""The two agent tools: OpenAI schemas + pure handlers.

Design: handlers take a plain `extracted` dict (the conversation's field store)
and the raw LLM args. They validate, mutate the dict, and return a small result
the model reacts to. No DB, no network here — persistence wraps these in P5, so
the whole screening logic stays unit-testable offline.

The model interprets the candidate; Python checks types and owns the outcome
(ADR-013, ADR-015): every answer returns the status computed from the data, so a
knock-out never depends on the model deciding to call a tool.

The same schemas register with both chat and the Realtime (voice) session; the
same handlers run for both transports (see propuesta-tecnica §03).
"""
from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from schemas import EndInterviewArgs, SaveAnswerArgs
from service_areas import cities, match_city

Result = dict[str, Any]


def _schema(name: str, description: str, args: type[BaseModel]) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description, "parameters": args.model_json_schema()}}


# ── OpenAI function schemas (registered in chat + reshaped for Realtime) ────────

OPENAI_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _schema("save_answer",
            "Save what the candidate just answered, as typed values. Several fields at once "
            "is fine. The result carries the screening status; on validation_error, re-ask.",
            SaveAnswerArgs),
    _schema("end_interview",
            "Close the interview with a 2-3 sentence summary and the candidate's tone for the "
            "recruiter. Call once, "
            "after the confirmation or after saying goodbye on a knock-out.",
            EndInterviewArgs),
]

# ── Status: always computed from the data (ADR-017) ─────────────────────────────


def screening_status(extracted: dict) -> tuple[str, str | None]:
    """(status, knock-out reason). Qualified = license + covered city; nothing else
    excludes. Recomputed on every answer, so a correction updates it."""
    if extracted.get("has_driver_license") is False:
        return "disqualified", "no_license"
    city = extracted.get("city")
    if city is not None and city not in cities():
        return "disqualified", "out_of_service_area"
    if extracted.get("has_driver_license") is True and city is not None:
        return "qualified", None
    return "pending", None


# ── Handlers (pure: mutate `extracted`, return a result) ────────────────────────


def save_answer(extracted: dict, args: dict) -> Result:
    values = SaveAnswerArgs.model_validate(args).model_dump(exclude_none=True, mode="json")
    if "city" in values:  # canonical name if covered; else keep the candidate's words
        values["city"] = match_city(values["city"]) or values["city"]
    extracted.update(values)
    status, knockout = screening_status(extracted)
    result: Result = {"ok": True, "status": status}
    if knockout:
        result["knockout"] = knockout
    if knockout == "out_of_service_area":
        result["covered_cities"] = cities()
    return result


def end_interview(extracted: dict, args: dict) -> Result:
    EndInterviewArgs.model_validate(args)
    return {"ok": True, "status": screening_status(extracted)[0]}


HANDLERS: dict[str, Callable[[dict, dict], Result]] = {
    "save_answer": save_answer,
    "end_interview": end_interview,
}


def dispatch(name: str, extracted: dict, args: dict) -> Result:
    """Run a tool call by name; never raise on bad args (returns an error result)."""
    handler = HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "validation_error": f"unknown tool {name}"}
    try:
        return handler(extracted, args)
    except ValidationError as e:
        err = e.errors()[0]
        field = ".".join(str(p) for p in err["loc"])
        return {"ok": False, "validation_error": f"{field}: {err['msg']}"}
