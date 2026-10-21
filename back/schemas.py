"""Pydantic contracts for the two agent tools (ADR-014, ADR-015).

The model turns the candidate's words into typed values; these models check the
types. The OpenAI tool schemas are generated from them, so the contract the
model sees and the validation Python runs can never drift apart.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Availability = Literal["full_time", "part_time", "weekends"]
Schedule = Literal["morning", "afternoon", "evening", "flexible"]


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
    contact_email: str | None = Field(None, min_length=3)

    @field_validator("start_date")
    @classmethod
    def _not_in_the_past(cls, v: date | None) -> date | None:
        if v is not None and v < date.today():
            raise ValueError("start date must be today or later")
        return v


class EndInterviewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, description="2-3 sentences for the recruiter.")
