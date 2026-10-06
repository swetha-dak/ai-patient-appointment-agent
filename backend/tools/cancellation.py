"""Cancel a specific appointment. Does not cancel a different patient's visit."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.tools.common import error, fetch_patient, ok, open_connection, require_text, row_to_dict
from backend.tools.safety import reject_if_not_booked, reject_wrong_appointment_patient


def cancel_appointment(appointment_id: str, patient_id: str) -> dict[str, Any]:
    appointment_id_or_error = require_text(appointment_id, "appointment_id")
    if isinstance(appointment_id_or_error, dict):
        return appointment_id_or_error
    patient_id_or_error = require_text(patient_id, "patient_id")
    if isinstance(patient_id_or_error, dict):
        return patient_id_or_error

    appointment_id = appointment_id_or_error
    patient_id = patient_id_or_error

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
        booked_error = reject_if_not_booked(appointment, "cancelled")
        if booked_error:
            connection.rollback()
            return booked_error

        connection.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE appointment_id = ?",
            (appointment_id,),
        )
        connection.execute(
            """
            UPDATE availability
            SET is_available = 1
            WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
            """,
            (appointment["doctor_id"], appointment["appointment_date"], appointment["appointment_time"]),
        )
        connection.commit()

        stored = connection.execute(
            "SELECT * FROM appointments WHERE appointment_id = ?",
            (appointment_id,),
        ).fetchone()
        if stored is None or stored["status"] != "cancelled":
            return error("CANCEL_NOT_CONFIRMED", "Update did not persist; appointment was not cancelled.")
        return ok(row_to_dict(stored))
    except sqlite3.Error as exc:
        connection.rollback()
        return error("DATABASE_ERROR", f"Cancellation failed: {exc}")
    finally:
        connection.close()
