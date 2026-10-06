"""JSON tool schemas for Ollama /api/chat. Execution still goes through Python tools."""

from __future__ import annotations

from typing import Any

OLLAMA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_patient",
            "description": "Look up a patient in SQLite. Do not guess if multiple patients match.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "name": {"type": "string"},
                    "date_of_birth": {"type": "string"},
                    "phone": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_patient",
            "description": "Insert a new patient into SQLite after lookup found no match. Requires name, date_of_birth, and phone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "date_of_birth": {"type": "string", "description": "YYYY-MM-DD"},
                    "phone": {"type": "string"},
                },
                "required": ["name", "date_of_birth", "phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Return real availability rows from SQLite. Never invent slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doctor_id": {"type": "string"},
                    "doctor_name": {"type": "string"},
                    "appointment_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "appointment_time": {"type": "string", "description": "HH:MM"},
                    "available_only": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": (
                "Book a slot in SQLite. The server ignores the confirmed argument from the model "
                "and sets it from explicit patient confirmation in conversation state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string"},
                    "doctor_id": {"type": "string"},
                    "appointment_date": {"type": "string"},
                    "appointment_time": {"type": "string"},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["patient_id", "doctor_id", "appointment_date", "appointment_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel one appointment. patient_id must own the appointment_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string"},
                    "patient_id": {"type": "string"},
                },
                "required": ["appointment_id", "patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": (
                "Move an appointment to a new SQLite slot after availability is checked. "
                "confirmed is set by the server from patient confirmation, not the model."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string"},
                    "patient_id": {"type": "string"},
                    "appointment_date": {"type": "string"},
                    "appointment_time": {"type": "string"},
                    "doctor_id": {"type": "string"},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["appointment_id", "patient_id", "appointment_date", "appointment_time"],
            },
        },
    },
]
