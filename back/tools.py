"""The agent tools: OpenAI schemas + handlers.

Design: handlers take a plain `extracted` dict (the conversation's field store)
and the raw LLM args. They validate, mutate the dict, and return a small result
the model reacts to. No DB here — persistence wraps these in P5, so the whole
screening logic stays unit-testable offline. The one exception to "no network"
is search_faq, which reads the FAQ (faq.py) and never touches `extracted`.

The model interprets the candidate; Python checks types and owns the outcome
(ADR-013, ADR-015): every answer returns the status computed from the data, so a
knock-out never depends on the model deciding to call a tool.

The same schemas register with both chat and the Realtime (voice) session; the
same handlers run for both transports (see propuesta-tecnica §03).
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

import faq
from schemas import (
    BookInterviewArgs,
    EndInterviewArgs,
    FindSlotsArgs,
    SaveAnswerArgs,
    SearchFaqArgs,
)
from service_areas import cities, match_city

Result = dict[str, Any]


def _schema(name: str, description: str, args: type[BaseModel]) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": name, "description": description, "parameters": args.model_json_schema()}}


# ── OpenAI function schemas (registered in chat + reshaped for Realtime) ────────

OPENAI_TOOL_SCHEMAS: list[dict[str, Any]] = [
    _schema("save_answer",
            "Save what the candidate just answered, as typed values: ONE call per candidate "
            "message, with every field it gave, and never a field the candidate did not say. "
            "The result carries the screening status; on validation_error, re-ask.",
            SaveAnswerArgs),
    _schema("end_interview",
            "Close the interview with a 2-3 sentence summary and the candidate's tone for the "
            "recruiter. Call once, "
            "after the confirmation or after saying goodbye on a knock-out.",
            EndInterviewArgs),
    _schema("find_slots",
            "Qualified candidates only: the 3 nearest open interview slots matching the "
            "candidate's preference (a day, a start date, morning/afternoon/evening).",
            FindSlotsArgs),
    _schema("book_interview",
            "Book the slot the candidate chose, by its number among the ones find_slots offered.",
            BookInterviewArgs),
    _schema("search_faq",
            "Look up the company FAQ when the candidate asks about the job (pay, vehicle, "
            "shifts, contract, next steps...). Answer only from the results.",
            SearchFaqArgs),
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


# ── Interview booking (ADR-032): fixed weekly pattern, no time zones, no locking ─

_SLOTS = Path(__file__).resolve().parent / "data" / "slots.json"
_PARTS = {"morning": (0, 14), "afternoon": (14, 20), "evening": (20, 24)}
INTERVIEW_KEY = "_interview_at"  # the turn's working copy only; persisted as its own column
# The last slots offered, kept with the data: the model's history is text only (ADR-025),
# so on the next turn it books by number and never has to rebuild a datetime from its words.
OFFERED_KEY = "_offered_slots"


def open_slots(now: datetime | None = None) -> list[datetime]:
    """Every slot of the weekly pattern from now to `days_ahead`, in order. Wall-clock
    times with no zone: the same hours count for Spain and Mexico (simplification)."""
    cfg = json.loads(_SLOTS.read_text("utf-8"))
    now = now or datetime.now()
    days = (now.date() + timedelta(days=d) for d in range(cfg["days_ahead"] + 1))
    return [s for day in days if day.weekday() in cfg["weekdays"]
            for s in (datetime.combine(day, time.fromisoformat(t)) for t in cfg["times"]) if s > now]


def find_slots(extracted: dict, args: dict) -> Result:
    if screening_status(extracted)[0] != "qualified":
        return {"ok": False, "validation_error": "only a qualified candidate can book an interview"}
    a = FindSlotsArgs.model_validate(args)
    lo, hi = _PARTS[a.part] if a.part else (0, 24)
    slots = [s for s in open_slots()
             if (a.day is None or s.date() == a.day)
             and (a.from_date is None or s.date() >= a.from_date)
             and lo <= s.hour < hi]
    extracted[OFFERED_KEY] = [s.isoformat(timespec="minutes") for s in slots[:3]]
    return {"ok": True, "slots": extracted[OFFERED_KEY]}


def book_interview(extracted: dict, args: dict) -> Result:
    if screening_status(extracted)[0] != "qualified":
        return {"ok": False, "validation_error": "only a qualified candidate can book an interview"}
    choice = BookInterviewArgs.model_validate(args).choice
    offered = extracted.get(OFFERED_KEY, [])
    if choice > len(offered) or datetime.fromisoformat(offered[choice - 1]) not in open_slots():
        return {"ok": False, "validation_error": "not an open slot: call find_slots and offer one of those"}
    extracted[INTERVIEW_KEY] = extracted.pop(OFFERED_KEY)[choice - 1]
    return {"ok": True, "interview_at": extracted[INTERVIEW_KEY]}


def search_faq(_extracted: dict, args: dict) -> Result:
    return faq.search(SearchFaqArgs.model_validate(args).query)


HANDLERS: dict[str, Callable[[dict, dict], Result]] = {
    "save_answer": save_answer,
    "end_interview": end_interview,
    "find_slots": find_slots,
    "book_interview": book_interview,
    "search_faq": search_faq,
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
