"""Structured NLU payload from Qwen. Not used as a source of truth for clinic data."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UserExtraction(BaseModel):
    intent: Literal["book", "cancel", "reschedule", "availability", "general"] | None = None
    patient_id: str | None = None
    patient_name: str | None = None
    doctor_name: str | None = None
    doctor_id: str | None = None
    appointment_id: str | None = None
    date_text: str | None = Field(default=None, description="Raw date words from the user, not a guessed ISO date.")
    time_text: str | None = Field(default=None, description="Raw time words from the user, not a guessed slot.")
    confirmation: bool = False
