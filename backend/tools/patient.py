"""Look up a patient in SQLite. Does not guess when the match is ambiguous."""

from __future__ import annotations

from typing import Any

from backend.tools.common import error, fetch_patient, ok, open_connection, row_to_dict


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def get_patient(
    patient_id: str | None = None,
    name: str | None = None,
    date_of_birth: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    patient_id = patient_id.strip().upper() if isinstance(patient_id, str) else patient_id
    name = " ".join(name.split()) if isinstance(name, str) else name
    date_of_birth = date_of_birth.strip() if isinstance(date_of_birth, str) else date_of_birth
    phone = phone.strip() if isinstance(phone, str) else phone

    if not any([patient_id, name, date_of_birth, phone]):
        return error("INVALID_INPUT", "Provide patient_id or at least one of name, date_of_birth, phone.")

    connection = open_connection()
    try:
        if patient_id:
            row = fetch_patient(connection, patient_id)
            if row is None:
                return error(
                    "PATIENT_NOT_FOUND",
                    f"No patient found for patient_id={patient_id}. That id is not in the clinic records.",
                )
            patient = row_to_dict(row)
            assert patient is not None
            if name and _normalize_name(patient["name"]) != _normalize_name(name):
                return error("PATIENT_MISMATCH", "Provided name does not match patient_id.")
            if date_of_birth and patient["date_of_birth"] != date_of_birth:
                return error("PATIENT_MISMATCH", "Provided date_of_birth does not match patient_id.")
            if phone and patient["phone"] != phone:
                return error("PATIENT_MISMATCH", "Provided phone does not match patient_id.")
            return ok(patient)

        query = "SELECT patient_id, name, date_of_birth, phone FROM patients WHERE 1=1"
        params: list[str] = []
        if name:
            token = name.split()[0]
            query += (
                " AND (LOWER(name) = LOWER(?)"
                " OR LOWER(name) LIKE LOWER(?) || '%'"
                " OR LOWER(name) LIKE '% ' || LOWER(?))"
            )
            params.extend([name, token, token])
        if date_of_birth:
            query += " AND date_of_birth = ?"
            params.append(date_of_birth)
        if phone:
            query += " AND phone = ?"
            params.append(phone)

        rows = connection.execute(query, params).fetchall()
        unique: dict[str, Any] = {}
        for row in rows:
            unique[row["patient_id"]] = row
        rows = list(unique.values())
        if not rows:
            return error(
                "PATIENT_NOT_FOUND",
                "That name is not in the clinic records. Provide a patient ID such as PAT-002, "
                "or a seeded full name such as Brian Cole.",
            )
        if len(rows) > 1:
            return error(
                "AMBIGUOUS_PATIENT",
                "Multiple patients matched. Provide patient_id or more identifying details.",
            )
        return ok(row_to_dict(rows[0]))
    finally:
        connection.close()
