"""Pydantic contracts for the agent tools (ADR-014, ADR-015, ADR-031).

The model turns the candidate's words into typed values; these models check the
types. The OpenAI tool schemas are generated from them, so the contract the
model sees and the validation Python runs can never drift apart.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Availability = Literal["full_time", "part_time", "weekends"]
Schedule = Literal["morning", "afternoon", "evening", "flexible"]
Sentiment = Literal["positive", "neutral", "frustrated"]


class Experience(BaseModel):
    model_config = ConfigDict(extra="forbid")
    years: int = Field(ge=0, le=80)
    platforms: list[str] = Field(description="Glovo, Uber Eats, ... Empty list = none.")


class SaveAnswerArgs(BaseModel):
    """Every field optional: send only what the candidate just answered."""
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(None, min_length=1, max_length=120)
    has_driver_license: bool | None = None
    city: str | None = Field(None, min_length=1, description="City as the candidate said it.")
    availability: list[Availability] | None = Field(None, min_length=1)
    preferred_schedule: list[Schedule] | None = Field(None, min_length=1)
    prior_experience: Experience | None = None
    start_date: date | None = Field(None, description="ISO yyyy-mm-dd, today or later.")

    @field_validator("start_date")
    @classmethod
    def _not_in_the_past(cls, v: date | None) -> date | None:
        if v is not None and v < date.today():
            raise ValueError("start date must be today or later")
        return v


class EndInterviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, description="2-3 sentences for the recruiter.")
    sentiment: Sentiment = Field(description="The candidate's tone in the conversation, not the outcome.")


class FindSlotsArgs(BaseModel):
    """The candidate's preference as filters; all optional ("cuando sea" = none)."""
    model_config = ConfigDict(extra="forbid")
    day: date | None = Field(None, description="A specific day the candidate asked for, ISO yyyy-mm-dd.")
    from_date: date | None = Field(None, description="Earliest day, if they said 'from Monday on', ISO.")
    part: Literal["morning", "afternoon", "evening"] | None = Field(
        None, description="morning < 14:00, afternoon 14:00-20:00, evening >= 20:00.")


class BookInterviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: datetime = Field(description="One of the slots find_slots returned, exactly as given.")


class SearchFaqArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=300, description="The candidate's doubt, in Spanish.")
