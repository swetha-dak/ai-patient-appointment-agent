"""Book an appointment only when SQLite confirms an open slot."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.tools.common import (
    error,
    fetch_doctor,
    fetch_patient,
    fetch_slot,
    next_prefixed_id,
    ok,
    open_connection,
    require_text,
    row_to_dict,
    validate_date,
    validate_time,
)
from backend.tools.safety import reject_missing_or_unavailable_slot, require_explicit_confirmation


def book_appointment(
    patient_id: str,
    doctor_id: str,
    appointment_date: str,
    appointment_time: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    confirmation_error = require_explicit_confirmation(confirmed, action="booking")
    if confirmation_error:
        return confirmation_error

    patient_id_or_error = require_text(patient_id, "patient_id")
    if isinstance(patient_id_or_error, dict):
        return patient_id_or_error
    doctor_id_or_error = require_text(doctor_id, "doctor_id")
    if isinstance(doctor_id_or_error, dict):
        return doctor_id_or_error
    date_or_error = require_text(appointment_date, "appointment_date")
    if isinstance(date_or_error, dict):
        return date_or_error
    time_or_error = require_text(appointment_time, "appointment_time")
    if isinstance(time_or_error, dict):
        return time_or_error

    patient_id = patient_id_or_error
    doctor_id = doctor_id_or_error
    appointment_date = date_or_error
    appointment_time = time_or_error

    date_error = validate_date(appointment_date)
    if date_error:
        return date_error
    time_error = validate_time(appointment_time)
    if time_error:
        return time_error

    connection = open_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        if fetch_patient(connection, patient_id) is None:
            connection.rollback()
            return error("PATIENT_NOT_FOUND", f"No patient found for patient_id={patient_id}.")
        if fetch_doctor(connection, doctor_id) is None:
            connection.rollback()
            return error("DOCTOR_NOT_FOUND", f"No doctor found for doctor_id={doctor_id}.")

        slot = fetch_slot(connection, doctor_id, appointment_date, appointment_time)
        slot_error = reject_missing_or_unavailable_slot(slot)
        if slot_error:
            connection.rollback()
            return slot_error

        existing = connection.execute(
            """
            SELECT appointment_id FROM appointments
            WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ? AND status = 'booked'
            """,
            (doctor_id, appointment_date, appointment_time),
        ).fetchone()
        if existing is not None:
            connection.rollback()
            return error("DOUBLE_BOOKING", "That slot is already booked.")

        appointment_id = next_prefixed_id(connection, "appointments", "appointment_id", "APT-")
        connection.execute(
            """
            INSERT INTO appointments (
                appointment_id, patient_id, doctor_id, appointment_date, appointment_time, status
            ) VALUES (?, ?, ?, ?, ?, 'booked')
            """,
            (appointment_id, patient_id, doctor_id, appointment_date, appointment_time),
        )
        connection.execute(
            """
            UPDATE availability
            SET is_available = 0
            WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
            """,
            (doctor_id, appointment_date, appointment_time),
        )
        connection.commit()

        stored = connection.execute(
            "SELECT * FROM appointments WHERE appointment_id = ?",
            (appointment_id,),
        ).fetchone()
        if stored is None:
            return error("BOOKING_NOT_CONFIRMED", "Insert did not persist; booking was not created.")
        return ok(row_to_dict(stored))
    except sqlite3.IntegrityError:
        connection.rollback()
        return error("DOUBLE_BOOKING", "That slot is already booked.")
    except sqlite3.Error as exc:
        connection.rollback()
        return error("DATABASE_ERROR", f"Booking failed: {exc}")
    finally:
        connection.close()
