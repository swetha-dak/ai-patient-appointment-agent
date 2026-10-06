"""SQLite connection and schema. The database is the source of truth."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = "data/clinic.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    phone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS doctors (
    doctor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS availability (
    availability_id TEXT PRIMARY KEY,
    doctor_id TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    is_available INTEGER NOT NULL CHECK (is_available IN (0, 1)),
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id),
    UNIQUE (doctor_id, appointment_date, appointment_time)
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    doctor_id TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('booked', 'cancelled')),
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_booked_slot
ON appointments(doctor_id, appointment_date, appointment_time)
WHERE status = 'booked';
"""


def get_database_path() -> Path:
    raw_path = os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def get_connection() -> sqlite3.Connection:
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_schema(connection: sqlite3.Connection | None = None) -> None:
    owns_connection = connection is None
    if owns_connection:
        connection = get_connection()
    assert connection is not None
    connection.executescript(SCHEMA_SQL)
    connection.commit()
    if owns_connection:
        connection.close()
