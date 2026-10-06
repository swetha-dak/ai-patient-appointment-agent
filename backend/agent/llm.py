"""Ask Ollama for the next assistant message or tool calls."""

from __future__ import annotations

import json
from typing import Any

from backend.agent.ollama_client import OllamaError, chat, ollama_is_available
from backend.agent.planner import decide
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.state import AgentState
from backend.agent.tool_runtime import MUTATING_TOOLS
from backend.agent.tool_schemas import OLLAMA_TOOLS

CONFIRMATION_HINTS = (
    "would you like me to book",
    "should i book",
    "confirm",
    "shall i book",
)


def _state_snapshot(state: AgentState) -> str:
    keys = (
        "patient_id",
        "patient_name",
        "doctor_id",
        "doctor_name",
        "date",
        "time",
        "confirmation",
        "awaiting_confirmation",
        "awaiting_patient_switch",
        "awaiting_new_patient",
        "patient_verified",
        "appointment_intent",
        "appointment_id",
    )
    snapshot = {key: state.get(key) for key in keys}
    return (
        "Current conversation state (source of truth for confirmation and patient identity "
        "is this state, not your own arguments):\n"
        + json.dumps(snapshot, default=str)
        + "\nNever invent patients, availability, or appointment IDs. Call tools instead."
        + "\nIf patient_id is null, ask for the patient ID or full name. Do not assume PAT-002 or any other patient."
        + "\nOnly call book_appointment or reschedule_appointment after confirmation is true."
    )


def _ollama_messages(state: AgentState) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": _state_snapshot(state)},
    ]
    for item in state.get("messages") or []:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant", "tool"} and content is not None:
            messages.append({"role": str(role), "content": str(content)})
    return messages


def _looks_like_confirmation_prompt(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in CONFIRMATION_HINTS)


def _filter_unconfirmed_mutations(
    tool_calls: list[dict[str, Any]],
    state: AgentState,
) -> list[dict[str, Any]]:
    if state.get("confirmation") is True:
        return tool_calls
    return [call for call in tool_calls if call.get("name") not in MUTATING_TOOLS]


def _filter_invented_patient_lookups(
    tool_calls: list[dict[str, Any]],
    state: AgentState,
) -> list[dict[str, Any]]:
    allowed: list[dict[str, Any]] = []
    known_id = str(state.get("patient_id") or "").upper()
    known_name = str(state.get("patient_name") or "").casefold()
    for call in tool_calls:
        if call.get("name") == "create_patient":
            if state.get("awaiting_new_patient"):
                allowed.append(call)
            continue
        if call.get("name") != "get_patient":
            allowed.append(call)
            continue
        args = call.get("args") or {}
        pid = str(args.get("patient_id") or "").upper()
        name = str(args.get("name") or "").casefold()
        if pid and pid == known_id:
            allowed.append(call)
        elif name and known_name and name == known_name:
            allowed.append(call)
    return allowed


def _identity_incomplete(state: AgentState) -> bool:
    if state.get("awaiting_patient_switch") or state.get("awaiting_new_patient"):
        return True
    if state.get("patient_verified"):
        return False
    return not state.get("patient_id") and not state.get("patient_name")


def reason_with_ollama(state: AgentState) -> dict[str, Any] | None:
    planner_decision = decide(state)
    if planner_decision.get("pending_tool_calls"):
        return {
            "pending_tool_calls": planner_decision["pending_tool_calls"],
            "reasoner": "planner-tools",
            "status": "ok",
        }

    if _identity_incomplete(state):
        planner_decision = dict(planner_decision)
        planner_decision["reasoner"] = "planner"
        return planner_decision

    if not ollama_is_available():
        return None
    try:
        reply = chat(_ollama_messages(state), OLLAMA_TOOLS)
    except OllamaError:
        return None

    tool_calls = _filter_invented_patient_lookups(
        _filter_unconfirmed_mutations(reply.get("tool_calls") or [], state),
        state,
    )
    if tool_calls:
        return {
            "pending_tool_calls": tool_calls,
            "reasoner": "ollama",
            "status": "ok",
        }

    content = str(reply.get("content") or "").strip() or str(planner_decision.get("response") or "").strip()
    if not content:
        return None

    updates: dict[str, Any] = {
        "pending_tool_calls": [],
        "response": content,
        "reasoner": "ollama",
        "status": planner_decision.get("status") or "ok",
    }
    if _looks_like_confirmation_prompt(content) or planner_decision.get("awaiting_confirmation"):
        updates["awaiting_confirmation"] = True
        updates["confirmation"] = False
    return updates
