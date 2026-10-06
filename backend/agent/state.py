"""Conversation state for the single LangGraph appointment agent."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from typing_extensions import TypedDict


def append_items(existing: list[Any] | None, new: list[Any] | None) -> list[Any]:
    return (existing or []) + (new or [])


Intent = Literal["book", "cancel", "reschedule", "unknown"]


class AgentState(TypedDict, total=False):
    session_id: str
    messages: Annotated[list[dict[str, Any]], append_items]
    patient_id: str | None
    patient_name: str | None
    doctor_id: str | None
    doctor_name: str | None
    date: str | None
    date_is_relative: bool
    time: str | None
    confirmation: bool
    awaiting_confirmation: bool
    awaiting_patient_switch: bool
    pending_patient_id: str | None
    pending_patient_name: str | None
    awaiting_new_patient: bool
    patient_dob: str | None
    patient_phone: str | None
    appointment_intent: Intent | None
    appointment_id: str | None
    patient_verified: bool
    offered_slots: list[dict[str, Any]]
    availability_fingerprint: str | None
    pending_tool_calls: list[dict[str, Any]]
    last_tool_results: list[dict[str, Any]]
    reasoner: str
    response: str
    status: str


def initial_state(session_id: str = "demo-session") -> AgentState:
    return {
        "session_id": session_id,
        "messages": [],
        "patient_id": None,
        "patient_name": None,
        "doctor_id": None,
        "doctor_name": None,
        "date": None,
        "date_is_relative": False,
        "time": None,
        "confirmation": False,
        "awaiting_confirmation": False,
        "awaiting_patient_switch": False,
        "pending_patient_id": None,
        "pending_patient_name": None,
        "awaiting_new_patient": False,
        "patient_dob": None,
        "patient_phone": None,
        "appointment_intent": None,
        "appointment_id": None,
        "patient_verified": False,
        "offered_slots": [],
        "availability_fingerprint": None,
        "pending_tool_calls": [],
        "last_tool_results": [],
        "reasoner": "",
        "response": "",
        "status": "ok",
    }
