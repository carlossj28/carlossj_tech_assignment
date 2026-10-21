"""Pydantic contracts for the four agent tools and the extracted-field store.

The LLM fills these via tool calls; handlers (tools.py) validate the values
the LLM can't check itself (city in service area, date in the future, yes/no).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Field7 = Literal[
    "full_name", "has_driver_license", "city", "availability",
    "preferred_schedule", "prior_experience", "start_date", "contact_email",
]

# The same 8 names as a plain list, for building the OpenAI tool schema.
FIELD_NAMES: list[str] = list(Field7.__args__)


class RecordFieldArgs(BaseModel):
    field: Field7
    value: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class FlagInvalidArgs(BaseModel):
    field: str
    user_value: str
    reason: str


class DisqualifyArgs(BaseModel):
    reason: Literal["no_license", "out_of_service_area"]
    detail: str


class CompleteScreeningArgs(BaseModel):
    summary: str
