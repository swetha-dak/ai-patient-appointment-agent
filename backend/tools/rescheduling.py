"""Reschedule only after SQLite shows the new slot is available."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.tools.common import (
    error,
    fetch_patient,
    fetch_slot,
    ok,
    open_connection,
    require_text,
    row_to_dict,
    validate_date,
    validate_time,
)
from backend.tools.safety import (
    reject_if_not_booked,
    reject_missing_or_unavailable_slot,
    reject_wrong_appointment_patient,
    require_explicit_confirmation,
)


def reschedule_appointment(
    appointment_id: str,
    patient_id: str,
    appointment_date: str,
    appointment_time: str,
    doctor_id: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    confirmation_error = require_explicit_confirmation(confirmed, action="rescheduling")
    if confirmation_error:
        return confirmation_error

    appointment_id_or_error = require_text(appointment_id, "appointment_id")
    if isinstance(appointment_id_or_error, dict):
        return appointment_id_or_error
    patient_id_or_error = require_text(patient_id, "patient_id")
    if isinstance(patient_id_or_error, dict):
        return patient_id_or_error
    date_or_error = require_text(appointment_date, "appointment_date")
    if isinstance(date_or_error, dict):
        return date_or_error
    time_or_error = require_text(appointment_time, "appointment_time")
    if isinstance(time_or_error, dict):
        return time_or_error

    appointment_id = appointment_id_or_error
    patient_id = patient_id_or_error
    appointment_date = date_or_error
    appointment_time = time_or_error
    doctor_id = doctor_id.strip() if isinstance(doctor_id, str) and doctor_id.strip() else None

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

        appointment = connection.execute(
            "SELECT * FROM appointments WHERE appointment_id = ?",
            (appointment_id,),
        ).fetchone()
        owner_error = reject_wrong_appointment_patient(appointment, patient_id)
        if owner_error:
            connection.rollback()
            return owner_error
        booked_error = reject_if_not_booked(appointment, "rescheduled")
        if booked_error:
            connection.rollback()
            return booked_error

        new_doctor_id = doctor_id or appointment["doctor_id"]
        same_slot = (
            new_doctor_id == appointment["doctor_id"]
            and appointment_date == appointment["appointment_date"]
            and appointment_time == appointment["appointment_time"]
        )
        if same_slot:
            connection.rollback()
            return error("SAME_SLOT", "The new slot is the same as the current appointment.")

        slot = fetch_slot(connection, new_doctor_id, appointment_date, appointment_time)
        slot_error = reject_missing_or_unavailable_slot(slot)
        if slot_error:
            connection.rollback()
            return slot_error

        conflict = connection.execute(
            """
            SELECT appointment_id FROM appointments
            WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
              AND status = 'booked' AND appointment_id != ?
            """,
            (new_doctor_id, appointment_date, appointment_time, appointment_id),
        ).fetchone()
        if conflict is not None:
            connection.rollback()
            return error("DOUBLE_BOOKING", "The requested new slot is already booked.")

        connection.execute(
            """
            UPDATE availability
            SET is_available = 1
            WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
            """,
            (appointment["doctor_id"], appointment["appointment_date"], appointment["appointment_time"]),
        )
        connection.execute(
            """
            UPDATE availability
            SET is_available = 0
            WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
            """,
            (new_doctor_id, appointment_date, appointment_time),
        )
        connection.execute(
            """
            UPDATE appointments
            SET doctor_id = ?, appointment_date = ?, appointment_time = ?
            WHERE appointment_id = ?
            """,
            (new_doctor_id, appointment_date, appointment_time, appointment_id),
        )
        connection.commit()

        stored = connection.execute(
            "SELECT * FROM appointments WHERE appointment_id = ?",
            (appointment_id,),
        ).fetchone()
        if stored is None:
            return error("RESCHEDULE_NOT_CONFIRMED", "Update did not persist; appointment was not rescheduled.")
        if (
            stored["doctor_id"] != new_doctor_id
            or stored["appointment_date"] != appointment_date
            or stored["appointment_time"] != appointment_time
            or stored["status"] != "booked"
        ):
            return error("RESCHEDULE_NOT_CONFIRMED", "Database state does not match the requested reschedule.")
        return ok(row_to_dict(stored))
    except sqlite3.IntegrityError:
        connection.rollback()
        return error("DOUBLE_BOOKING", "The requested new slot is already booked.")
    except sqlite3.Error as exc:
        connection.rollback()
        return error("DATABASE_ERROR", f"Reschedule failed: {exc}")
    finally:
        connection.close()
