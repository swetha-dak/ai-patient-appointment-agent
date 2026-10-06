"""Deterministic safety rules. The LLM is not the safety mechanism."""

from __future__ import annotations

from typing import Any

import sqlite3

from backend.tools.common import error


def require_explicit_confirmation(confirmed: object, action: str = "booking") -> dict[str, Any] | None:
    """Reject anything other than boolean True. Strings such as 'yes' do not count."""
    if confirmed is True:
        return None
    return error(
        "CONFIRMATION_REQUIRED",
        f"{action.capitalize()} was rejected because confirmed must be True.",
    )


def reject_missing_or_unavailable_slot(slot: sqlite3.Row | None) -> dict[str, Any] | None:
    if slot is None:
        return error(
            "SLOT_NOT_FOUND",
            "That date and time are not in the clinic schedule for this doctor.",
        )
    if not slot["is_available"]:
        return error("SLOT_UNAVAILABLE", "That slot is not available.")
    return None


def reject_wrong_appointment_patient(
    appointment: sqlite3.Row | None,
    patient_id: str,
) -> dict[str, Any] | None:
    if appointment is None:
        return error("APPOINTMENT_NOT_FOUND", "No appointment found for the given appointment_id.")
    if appointment["patient_id"] != patient_id:
        return error("APPOINTMENT_MISMATCH", "That appointment does not belong to this patient.")
    return None


def reject_if_not_booked(appointment: sqlite3.Row, action: str) -> dict[str, Any] | None:
    if appointment["status"] != "booked":
        return error("APPOINTMENT_NOT_BOOKED", f"Only a booked appointment can be {action}.")
    return None
