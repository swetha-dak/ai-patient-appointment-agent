"""In-memory multi-turn session store. No Redis; one process, keyed by session_id."""

from __future__ import annotations

from copy import deepcopy

from backend.agent.agent import run_turn
from backend.agent.state import AgentState, initial_state

MAX_MESSAGES = 40

_sessions: dict[str, AgentState] = {}


def get_session(session_id: str) -> AgentState:
    stored = _sessions.get(session_id)
    if stored is None:
        return initial_state(session_id)
    return deepcopy(stored)


def save_session(state: AgentState) -> None:
    session_id = str(state.get("session_id") or "demo-session")
    snapshot: AgentState = deepcopy(dict(state))
    snapshot["session_id"] = session_id
    snapshot["pending_tool_calls"] = []
    messages = list(snapshot.get("messages") or [])
    if len(messages) > MAX_MESSAGES:
        snapshot["messages"] = messages[-MAX_MESSAGES:]
    _sessions[session_id] = snapshot


def run_session_turn(session_id: str, user_message: str) -> AgentState:
    state = get_session(session_id)
    state["session_id"] = session_id
    result = run_turn(user_message, state)
    result["session_id"] = session_id
    save_session(result)
    return result


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def clear_all_sessions() -> None:
    _sessions.clear()


def session_snapshot(session_id: str) -> dict[str, object]:
    state = get_session(session_id)
    return {
        "session_id": state.get("session_id"),
        "patient_id": state.get("patient_id"),
        "patient_name": state.get("patient_name"),
        "doctor_id": state.get("doctor_id"),
        "doctor_name": state.get("doctor_name"),
        "date": state.get("date"),
        "time": state.get("time"),
        "confirmation": state.get("confirmation"),
        "awaiting_confirmation": state.get("awaiting_confirmation"),
        "awaiting_patient_switch": state.get("awaiting_patient_switch"),
        "patient_verified": state.get("patient_verified"),
        "appointment_intent": state.get("appointment_intent"),
        "appointment_id": state.get("appointment_id"),
    }
