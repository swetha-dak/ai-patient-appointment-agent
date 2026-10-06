"""Load fictional clinic data into SQLite. No real patient data."""

from __future__ import annotations

import sqlite3
import sys

from backend.database.database import get_connection, init_schema

PATIENTS = [
    ("PAT-001", "Alice Nguyen", "1988-04-12", "555-0101"),
    ("PAT-002", "Brian Cole", "1975-11-03", "555-0102"),
    ("PAT-003", "Maya Patel", "1992-07-21", "555-0103"),
    ("PAT-004", "Jordan Lee", "2001-01-09", "555-0104"),
]

DOCTORS = [
    ("DOC-001", "Dr. Smith", "Cardiology"),
    ("DOC-002", "Dr. Chen", "Pediatrics"),
    ("DOC-003", "Dr. Rivera", "Dermatology"),
]

# Fixed dates so seed data stays deterministic for later evaluation.
AVAILABILITY = [
    ("AVL-001", "DOC-001", "2026-10-06", "09:00", 1),
    ("AVL-002", "DOC-001", "2026-10-06", "10:00", 1),
    ("AVL-003", "DOC-001", "2026-10-06", "11:00", 0),
    ("AVL-004", "DOC-001", "2026-10-07", "09:00", 1),
    ("AVL-005", "DOC-002", "2026-10-06", "09:00", 1),
    ("AVL-006", "DOC-002", "2026-10-07", "14:00", 1),
    ("AVL-007", "DOC-003", "2026-10-08", "15:00", 1),
    ("AVL-008", "DOC-003", "2026-10-08", "16:00", 1),
]

APPOINTMENTS = [
    ("APT-001", "PAT-001", "DOC-001", "2026-10-06", "11:00", "booked"),
]


def _table_is_empty(connection: sqlite3.Connection, table_name: str) -> bool:
    allowed = {"patients", "doctors", "availability", "appointments"}
    if table_name not in allowed:
        raise ValueError(f"Unknown table: {table_name}")
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"]) == 0


def _clear_tables(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM appointments")
    connection.execute("DELETE FROM availability")
    connection.execute("DELETE FROM doctors")
    connection.execute("DELETE FROM patients")


def seed_database(reset: bool = False) -> None:
    connection = get_connection()
    try:
        init_schema(connection)
        empty = _table_is_empty(connection, "patients")
        if not empty and not reset:
            print("Database already has data. Re-run with --reset to replace it.")
            return
        if reset:
            _clear_tables(connection)
        connection.executemany(
            "INSERT INTO patients (patient_id, name, date_of_birth, phone) VALUES (?, ?, ?, ?)",
            PATIENTS,
        )
        connection.executemany(
            "INSERT INTO doctors (doctor_id, name, specialty) VALUES (?, ?, ?)",
            DOCTORS,
        )
        connection.executemany(
            """
            INSERT INTO availability (
                availability_id, doctor_id, appointment_date, appointment_time, is_available
            ) VALUES (?, ?, ?, ?, ?)
            """,
            AVAILABILITY,
        )
        connection.executemany(
            """
            INSERT INTO appointments (
                appointment_id, patient_id, doctor_id, appointment_date, appointment_time, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            APPOINTMENTS,
        )
        connection.commit()
        print(f"Seeded database at {connection.execute('PRAGMA database_list').fetchone()['file']}")
        print(f"patients={len(PATIENTS)} doctors={len(DOCTORS)} "
              f"availability={len(AVAILABILITY)} appointments={len(APPOINTMENTS)}")
    finally:
        connection.close()


if __name__ == "__main__":
    seed_database(reset="--reset" in sys.argv)
