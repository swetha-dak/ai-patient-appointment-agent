"""Return doctor availability from SQLite only. Never invents slots."""

from __future__ import annotations

from typing import Any

from backend.tools.common import (
    error,
    fetch_doctor,
    ok,
    open_connection,
    row_to_dict,
    validate_date,
    validate_time,
)


def check_availability(
    doctor_id: str | None = None,
    doctor_name: str | None = None,
    appointment_date: str | None = None,
    appointment_time: str | None = None,
    available_only: bool = True,
) -> dict[str, Any]:
    doctor_id = doctor_id.strip() if isinstance(doctor_id, str) else doctor_id
    doctor_name = doctor_name.strip() if isinstance(doctor_name, str) else doctor_name
    appointment_date = appointment_date.strip() if isinstance(appointment_date, str) else appointment_date
    appointment_time = appointment_time.strip() if isinstance(appointment_time, str) else appointment_time

    if appointment_date:
        date_error = validate_date(appointment_date)
        if date_error:
            return date_error
    if appointment_time:
        time_error = validate_time(appointment_time)
        if time_error:
            return time_error

    connection = open_connection()
    try:
        resolved_doctor_id = doctor_id
        if doctor_id:
            doctor = fetch_doctor(connection, doctor_id)
            if doctor is None:
                return error("DOCTOR_NOT_FOUND", f"No doctor found for doctor_id={doctor_id}.")
        elif doctor_name:
            matches = connection.execute(
                """
                SELECT doctor_id, name, specialty FROM doctors
                WHERE LOWER(name) = LOWER(?)
                   OR LOWER(name) LIKE '%' || LOWER(?)
                """,
                (doctor_name, doctor_name.casefold()),
            ).fetchall()
            if not matches:
                return error("DOCTOR_NOT_FOUND", f"No doctor found for name={doctor_name}.")
            if len(matches) > 1:
                return error("AMBIGUOUS_DOCTOR", "Multiple doctors matched that name. Provide doctor_id.")
            resolved_doctor_id = matches[0]["doctor_id"]
        else:
            return error("INVALID_INPUT", "Provide doctor_id or doctor_name.")

        query = """
            SELECT availability_id, doctor_id, appointment_date, appointment_time, is_available
            FROM availability
            WHERE doctor_id = ?
        """
        params: list[str] = [resolved_doctor_id]
        if appointment_date:
            query += " AND appointment_date = ?"
            params.append(appointment_date)
        if appointment_time:
            query += " AND appointment_time = ?"
            params.append(appointment_time)
        if available_only:
            query += " AND is_available = 1"
        query += " ORDER BY appointment_date, appointment_time"

        slots = [row_to_dict(row) for row in connection.execute(query, params).fetchall()]
        return ok(
            {
                "doctor_id": resolved_doctor_id,
                "slots": slots,
            }
        )
    finally:
        connection.close()
