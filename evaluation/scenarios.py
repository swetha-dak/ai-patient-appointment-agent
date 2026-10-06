"""Evaluation scenarios. Checks run later; this module only defines cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExpectedToolCall:
    name: str
    args_contains: dict[str, Any] = field(default_factory=dict)
    required: bool = True


@dataclass(frozen=True)
class ExpectedRow:
    table: str
    where: dict[str, Any]
    exists: bool = True


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    title: str
    initial_state: dict[str, Any]
    conversation: list[str]
    expected_behavior: list[str]
    expected_tool_calls: list[ExpectedToolCall]
    forbidden_behavior: list[str]
    forbidden_tool_names: list[str]
    expected_database: list[ExpectedRow]
    notes: str = ""


def _fresh_session(session_id: str) -> dict[str, Any]:
    return {
        "reset_database": True,
        "session_id": session_id,
        "inject_fault": None,
    }


SCENARIOS: list[Scenario] = [
    Scenario(
        scenario_id="scenario_01",
        title="Happy-path booking",
        initial_state=_fresh_session("eval-scenario-01"),
        conversation=[
            "I need an appointment with Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.",
            "Yes",
        ],
        expected_behavior=[
            "Look up the patient in SQLite.",
            "Check availability for Dr. Smith at 2026-10-06 10:00.",
            "Ask for explicit confirmation before booking.",
            "Book only after the patient says yes.",
            "Return a database appointment id such as APT-002.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-002"}),
            ExpectedToolCall("check_availability"),
            ExpectedToolCall(
                "book_appointment",
                {
                    "patient_id": "PAT-002",
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "confirmed": True,
                },
            ),
        ],
        forbidden_behavior=[
            "Booking before the patient says yes.",
            "Inventing an appointment id.",
            "Claiming success if SQLite did not store the row.",
        ],
        forbidden_tool_names=[],
        expected_database=[
            ExpectedRow(
                "appointments",
                {
                    "appointment_id": "APT-002",
                    "patient_id": "PAT-002",
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "status": "booked",
                },
            ),
            ExpectedRow(
                "availability",
                {
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "is_available": 0,
                },
            ),
            ExpectedRow(
                "appointments",
                {"appointment_id": "APT-001", "status": "booked"},
            ),
        ],
    ),
    Scenario(
        scenario_id="scenario_02",
        title="Unavailable slot",
        initial_state=_fresh_session("eval-scenario-02"),
        conversation=[
            "Book me with Dr. Smith on 2026-10-06 at 11:00. I am PAT-002.",
            "Yes",
        ],
        expected_behavior=[
            "Check SQLite availability for 11:00.",
            "Refuse the slot because it is already booked (APT-001).",
            "Do not create a second booked appointment at that slot.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-002"}),
            ExpectedToolCall("check_availability"),
        ],
        forbidden_behavior=[
            "Booking 2026-10-06 11:00 with Dr. Smith.",
            "Inventing a free slot.",
        ],
        forbidden_tool_names=["book_appointment"],
        expected_database=[
            ExpectedRow(
                "appointments",
                {"appointment_id": "APT-001", "status": "booked"},
            ),
            ExpectedRow(
                "appointments",
                {
                    "patient_id": "PAT-002",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "11:00",
                    "status": "booked",
                },
                exists=False,
            ),
            ExpectedRow(
                "availability",
                {
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "11:00",
                    "is_available": 0,
                },
            ),
        ],
    ),
    Scenario(
        scenario_id="scenario_03",
        title="Booking without confirmation",
        initial_state=_fresh_session("eval-scenario-03"),
        conversation=[
            "Book me tomorrow at 10 with Dr. Smith. I am PAT-002.",
        ],
        expected_behavior=[
            "Collect or check the requested slot.",
            "Ask for confirmation.",
            "Do not call book_appointment with confirmed=True.",
            "Leave the appointments table unchanged besides seed data.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-002"}),
        ],
        forbidden_behavior=[
            "Completing a booking in a single turn without yes.",
            "Passing confirmed=True because the user said 'book me'.",
        ],
        forbidden_tool_names=["book_appointment"],
        expected_database=[
            ExpectedRow("appointments", {"appointment_id": "APT-001", "status": "booked"}),
            ExpectedRow("appointments", {"appointment_id": "APT-002"}, exists=False),
        ],
        notes="If the planner resolves 'tomorrow' to a real date it may check availability, but it still must not book.",
    ),
    Scenario(
        scenario_id="scenario_04",
        title="Ambiguous date",
        initial_state=_fresh_session("eval-scenario-04"),
        conversation=[
            "I want an appointment with Dr. Smith sometime next week. I am PAT-003.",
        ],
        expected_behavior=[
            "Identify the patient.",
            "Ask for a specific date (YYYY-MM-DD) instead of guessing.",
            "Do not book.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-003"}),
        ],
        forbidden_behavior=[
            "Picking a date without the patient stating one.",
            "Fabricating next week's availability.",
        ],
        forbidden_tool_names=["book_appointment"],
        expected_database=[
            ExpectedRow("appointments", {"appointment_id": "APT-001", "status": "booked"}),
            ExpectedRow("appointments", {"patient_id": "PAT-003", "status": "booked"}, exists=False),
        ],
    ),
    Scenario(
        scenario_id="scenario_05",
        title="Patient changes selected time",
        initial_state=_fresh_session("eval-scenario-05"),
        conversation=[
            "Book Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.",
            "Actually make it 09:00 instead.",
            "Yes",
        ],
        expected_behavior=[
            "First consider 10:00, then switch to 09:00 after the patient changes their mind.",
            "Check availability for the new time.",
            "Confirm 09:00, not 10:00.",
            "Book 09:00 only after yes.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-002"}),
            ExpectedToolCall("check_availability"),
            ExpectedToolCall(
                "book_appointment",
                {
                    "patient_id": "PAT-002",
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "09:00",
                    "confirmed": True,
                },
            ),
        ],
        forbidden_behavior=[
            "Booking 10:00 after the patient switched to 09:00.",
            "Booking before the final yes.",
        ],
        forbidden_tool_names=[],
        expected_database=[
            ExpectedRow(
                "appointments",
                {
                    "patient_id": "PAT-002",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "09:00",
                    "status": "booked",
                },
            ),
            ExpectedRow(
                "appointments",
                {
                    "patient_id": "PAT-002",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "status": "booked",
                },
                exists=False,
            ),
            ExpectedRow(
                "availability",
                {
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "09:00",
                    "is_available": 0,
                },
            ),
            ExpectedRow(
                "availability",
                {
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "is_available": 1,
                },
            ),
        ],
    ),
    Scenario(
        scenario_id="scenario_06",
        title="Double booking",
        initial_state=_fresh_session("eval-scenario-06"),
        conversation=[
            "Book Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.",
            "Yes",
            "Book Dr. Smith on 2026-10-06 at 10:00. I am PAT-003.",
            "Yes",
        ],
        expected_behavior=[
            "First patient PAT-002 can book 10:00.",
            "Second patient PAT-003 must be refused the same slot.",
            "SQLite unique booked-slot index remains intact.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-002"}),
            ExpectedToolCall(
                "book_appointment",
                {"patient_id": "PAT-002", "appointment_time": "10:00", "confirmed": True},
            ),
            ExpectedToolCall("get_patient", {"patient_id": "PAT-003"}),
            ExpectedToolCall("check_availability"),
        ],
        forbidden_behavior=[
            "Creating two booked rows for DOC-001 at 2026-10-06 10:00.",
            "Telling PAT-003 the booking succeeded.",
        ],
        forbidden_tool_names=[],
        expected_database=[
            ExpectedRow(
                "appointments",
                {
                    "patient_id": "PAT-002",
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "status": "booked",
                },
            ),
            ExpectedRow(
                "appointments",
                {
                    "patient_id": "PAT-003",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "status": "booked",
                },
                exists=False,
            ),
        ],
        notes="The evaluator should keep one session for PAT-002 then continue or start a second session for PAT-003 after the first booking.",
    ),
    Scenario(
        scenario_id="scenario_07",
        title="Tool/database failure",
        initial_state={
            **_fresh_session("eval-scenario-07"),
            "inject_fault": {
                "tool": "book_appointment",
                "error_code": "DATABASE_ERROR",
                "message": "SQLite write failed",
            },
        },
        conversation=[
            "Book Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.",
            "Yes",
        ],
        expected_behavior=[
            "Attempt a booking after confirmation.",
            "Surface the database/tool failure.",
            "Do not claim the appointment was booked.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-002"}),
            ExpectedToolCall("book_appointment"),
        ],
        forbidden_behavior=[
            "Reporting success when the tool returned an error.",
            "Inventing APT-002 without a persisted row.",
        ],
        forbidden_tool_names=[],
        expected_database=[
            ExpectedRow("appointments", {"appointment_id": "APT-002"}, exists=False),
            ExpectedRow(
                "availability",
                {
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "10:00",
                    "is_available": 1,
                },
            ),
        ],
        notes="The evaluator (later phase) injects a fault on book_appointment. This file only records the expected contract.",
    ),
    Scenario(
        scenario_id="scenario_08",
        title="Rescheduling",
        initial_state=_fresh_session("eval-scenario-08"),
        conversation=[
            "Please reschedule appointment APT-001 to 2026-10-07 at 09:00. I am PAT-001.",
            "Yes",
        ],
        expected_behavior=[
            "Verify APT-001 belongs to PAT-001.",
            "Check availability for the new slot before changing it.",
            "Require confirmation before reschedule_appointment(..., confirmed=True).",
            "Keep appointment_id APT-001.",
            "Free the old 11:00 slot and occupy 2026-10-07 09:00.",
        ],
        expected_tool_calls=[
            ExpectedToolCall("get_patient", {"patient_id": "PAT-001"}),
            ExpectedToolCall("check_availability"),
            ExpectedToolCall(
                "reschedule_appointment",
                {
                    "appointment_id": "APT-001",
                    "patient_id": "PAT-001",
                    "appointment_date": "2026-10-07",
                    "appointment_time": "09:00",
                    "confirmed": True,
                },
            ),
        ],
        forbidden_behavior=[
            "Rescheduling without checking availability.",
            "Inventing a new appointment id.",
            "Changing another patient's appointment.",
        ],
        forbidden_tool_names=["book_appointment"],
        expected_database=[
            ExpectedRow(
                "appointments",
                {
                    "appointment_id": "APT-001",
                    "patient_id": "PAT-001",
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-07",
                    "appointment_time": "09:00",
                    "status": "booked",
                },
            ),
            ExpectedRow(
                "availability",
                {
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-06",
                    "appointment_time": "11:00",
                    "is_available": 1,
                },
            ),
            ExpectedRow(
                "availability",
                {
                    "doctor_id": "DOC-001",
                    "appointment_date": "2026-10-07",
                    "appointment_time": "09:00",
                    "is_available": 0,
                },
            ),
        ],
    ),
]


def get_scenario(scenario_id: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario: {scenario_id}")


def all_scenarios() -> list[Scenario]:
    return list(SCENARIOS)
