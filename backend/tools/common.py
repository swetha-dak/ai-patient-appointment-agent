"""Shared structured tool results. Tools never invent database rows."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from backend.database import get_connection

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "error": None, "data": data}


def error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}, "data": None}


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    if "is_available" in payload:
        payload["is_available"] = bool(payload["is_available"])
    return payload


def require_text(value: str | None, field: str) -> str | dict[str, Any]:
    if value is None or not str(value).strip():
        return error("INVALID_INPUT", f"{field} is required.")
    return str(value).strip()


def validate_date(value: str) -> dict[str, Any] | None:
    if not DATE_PATTERN.match(value):
        return error("INVALID_INPUT", "appointment_date must be YYYY-MM-DD.")
    return None


def validate_time(value: str) -> dict[str, Any] | None:
    if not TIME_PATTERN.match(value):
        return error("INVALID_INPUT", "appointment_time must be HH:MM.")
    return None


def fetch_patient(connection: sqlite3.Connection, patient_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT patient_id, name, date_of_birth, phone FROM patients WHERE UPPER(patient_id) = UPPER(?)",
        (patient_id.strip(),),
    ).fetchone()


def fetch_doctor(connection: sqlite3.Connection, doctor_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT doctor_id, name, specialty FROM doctors WHERE doctor_id = ?",
        (doctor_id,),
    ).fetchone()


def fetch_slot(
    connection: sqlite3.Connection,
    doctor_id: str,
    appointment_date: str,
    appointment_time: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT availability_id, doctor_id, appointment_date, appointment_time, is_available
        FROM availability
        WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
        """,
        (doctor_id, appointment_date, appointment_time),
    ).fetchone()


def next_prefixed_id(connection: sqlite3.Connection, table: str, column: str, prefix: str) -> str:
    allowed = {
        ("appointments", "appointment_id"): 5,
        ("patients", "patient_id"): 5,
    }
    key = (table, column)
    if key not in allowed:
        raise ValueError(f"Unsupported id sequence: {table}.{column}")
    start = allowed[key]
    row = connection.execute(
        f"SELECT MAX(CAST(SUBSTR({column}, ?) AS INTEGER)) AS max_n FROM {table}",
        (start,),
    ).fetchone()
    next_n = int(row["max_n"] or 0) + 1
    return f"{prefix}{next_n:03d}"


def open_connection() -> sqlite3.Connection:
    return get_connection()
