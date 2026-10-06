"""Insert a new fictional clinic patient into SQLite."""

from __future__ import annotations

from typing import Any

from backend.tools.common import (
    error,
    next_prefixed_id,
    ok,
    open_connection,
    require_text,
    row_to_dict,
    validate_date,
)


def _title_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split())


def create_patient(
    name: str,
    date_of_birth: str,
    phone: str,
) -> dict[str, Any]:
    name_or_error = require_text(name, "name")
    if isinstance(name_or_error, dict):
        return name_or_error
    dob_or_error = require_text(date_of_birth, "date_of_birth")
    if isinstance(dob_or_error, dict):
        return dob_or_error
    phone_or_error = require_text(phone, "phone")
    if isinstance(phone_or_error, dict):
        return phone_or_error

    date_error = validate_date(str(dob_or_error))
    if date_error:
        return date_error

    digits = "".join(ch for ch in str(phone_or_error) if ch.isdigit())
    if len(digits) < 7:
        return error("INVALID_INPUT", "phone must contain at least 7 digits.")

    stored_name = _title_name(str(name_or_error))
    connection = open_connection()
    try:
        existing = connection.execute(
            "SELECT patient_id, name, date_of_birth, phone FROM patients WHERE LOWER(name) = LOWER(?)",
            (stored_name,),
        ).fetchone()
        if existing is not None:
            return ok(row_to_dict(existing))

        patient_id = next_prefixed_id(connection, "patients", "patient_id", "PAT-")
        connection.execute(
            "INSERT INTO patients (patient_id, name, date_of_birth, phone) VALUES (?, ?, ?, ?)",
            (patient_id, stored_name, str(dob_or_error), digits),
        )
        connection.commit()
        row = connection.execute(
            "SELECT patient_id, name, date_of_birth, phone FROM patients WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        return ok(row_to_dict(row))
    finally:
        connection.close()
