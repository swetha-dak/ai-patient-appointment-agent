"""Single LangGraph appointment agent. Tools and SQLite enforce safety."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agent.extraction import extract_from_message
from backend.agent.llm import reason_with_ollama
from backend.agent.planner import decide
from backend.agent.state import AgentState, initial_state
from backend.agent.tool_runtime import execute_tool_call

YES_PREFIXES = ("yes", "yeah", "yep", "y", "ok", "okay")
NO_PREFIXES = ("no", "nope")
PATIENT_ID_RE = re.compile(r"\bPAT-\d+\b", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{6,}\d)")
NAME_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z'-]*$")
IDENTITY_PROMPT_HINTS = (
    "patient id",
    "full name",
    "date of birth",
    "clinic records",
    "new patient",
    "phone number",
)


def _last_message(state: AgentState) -> dict[str, Any] | None:
    messages = state.get("messages") or []
    if not messages:
        return None
    return messages[-1]


def _truthy_yes(text: str) -> bool:
    first = text.strip().split()[0].rstrip(".,!").lower() if text.strip() else ""
    return first in YES_PREFIXES


def _truthy_no(text: str) -> bool:
    first = text.strip().split()[0].rstrip(".,!").lower() if text.strip() else ""
    return first in NO_PREFIXES


def _digits_phone(text: str) -> str | None:
    scrubbed = ISO_DATE_RE.sub(" ", text)
    match = PHONE_RE.search(scrubbed)
    if not match:
        digits = "".join(ch for ch in scrubbed if ch.isdigit())
        return digits if len(digits) >= 7 else None
    digits = "".join(ch for ch in match.group(0) if ch.isdigit())
    return digits if len(digits) >= 7 else None


def _asked_for_identity(state: AgentState) -> bool:
    for item in reversed(state.get("messages") or []):
        if item.get("role") != "assistant":
            continue
        content = str(item.get("content") or "").lower()
        return any(hint in content for hint in IDENTITY_PROMPT_HINTS)
    return False


def _standalone_name(text: str) -> str | None:
    stripped = text.strip().strip(".,!")
    if not stripped or PATIENT_ID_RE.search(stripped):
        return None
    first = stripped.split()[0].rstrip(".,!").lower() if stripped else ""
    if first in YES_PREFIXES or first in NO_PREFIXES:
        return None
    if re.search(r"\b(appointment|book|cancel|reschedule|doctor|dr\.?|available|slot)\b", stripped, re.I):
        return None
    words = stripped.split()
    if 1 <= len(words) <= 4 and all(NAME_TOKEN_RE.fullmatch(word) for word in words):
        return " ".join(words)
    return None


def _normalize_patient_id(value: object) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _names_differ(left: object, right: object) -> bool:
    a = str(left or "").strip().casefold()
    b = str(right or "").strip().casefold()
    return bool(a and b and a != b)


def _apply_patient_identity(state: AgentState, extracted: dict[str, Any], text: str) -> dict[str, Any]:
    if state.get("awaiting_patient_switch") and _truthy_yes(text):
        extracted["patient_id"] = state.get("pending_patient_id")
        extracted["patient_name"] = state.get("pending_patient_name")
        extracted["patient_verified"] = False
        extracted["awaiting_patient_switch"] = False
        extracted["pending_patient_id"] = None
        extracted["pending_patient_name"] = None
        extracted["confirmation"] = False
        extracted["awaiting_confirmation"] = False
        return extracted

    if state.get("awaiting_patient_switch") and _truthy_no(text):
        extracted.pop("patient_id", None)
        extracted.pop("patient_name", None)
        extracted["awaiting_patient_switch"] = False
        extracted["pending_patient_id"] = None
        extracted["pending_patient_name"] = None
        return extracted

    established = bool(state.get("patient_verified") and state.get("patient_id"))
    incoming_id = _normalize_patient_id(extracted.get("patient_id"))
    incoming_name = extracted.get("patient_name")
    current_id = _normalize_patient_id(state.get("patient_id"))

    if established and incoming_id and incoming_id != current_id:
        extracted.pop("patient_id", None)
        extracted.pop("patient_name", None)
        extracted["pending_patient_id"] = incoming_id
        extracted["pending_patient_name"] = incoming_name
        extracted["awaiting_patient_switch"] = True
        extracted["confirmation"] = False
        extracted["awaiting_confirmation"] = False
        return extracted

    if established and incoming_name and _names_differ(incoming_name, state.get("patient_name")) and not incoming_id:
        extracted.pop("patient_name", None)
        extracted["pending_patient_name"] = incoming_name
        extracted["pending_patient_id"] = None
        extracted["awaiting_patient_switch"] = True
        extracted["confirmation"] = False
        extracted["awaiting_confirmation"] = False
        return extracted

    if state.get("awaiting_new_patient") and incoming_name and _names_differ(incoming_name, state.get("patient_name")):
        extracted["awaiting_new_patient"] = False
        extracted["patient_dob"] = None
        extracted["patient_phone"] = None
        extracted["patient_verified"] = False
        return extracted

    if incoming_id:
        extracted["patient_id"] = incoming_id
        if incoming_id != current_id:
            extracted["patient_verified"] = False
    return extracted


def ingest_and_plan(state: AgentState) -> dict[str, Any]:
    last = _last_message(state)
    updates: dict[str, Any] = {}
    merged: AgentState = dict(state)

    if last and last.get("role") == "user":
        text = str(last.get("content") or "")
        extracted = extract_from_message(text)
        if (
            not extracted.get("patient_id")
            and not extracted.get("patient_name")
            and not state.get("patient_verified")
            and _asked_for_identity(state)
        ):
            standalone = _standalone_name(text)
            if standalone:
                extracted["patient_name"] = standalone
        if state.get("awaiting_new_patient"):
            iso = ISO_DATE_RE.search(text)
            if iso:
                extracted["patient_dob"] = iso.group(1)
                extracted.pop("date", None)
            phone = _digits_phone(text)
            if phone:
                extracted["patient_phone"] = phone
        extracted = _apply_patient_identity(state, extracted, text)
        extracted["last_tool_results"] = []
        slot_keys = ("date", "time", "doctor_id", "doctor_name")
        if any(extracted.get(key) and extracted.get(key) != state.get(key) for key in slot_keys):
            extracted["availability_fingerprint"] = None
            extracted["offered_slots"] = []
            extracted["confirmation"] = False
            extracted["awaiting_confirmation"] = False
        if extracted.get("doctor_name") and extracted.get("doctor_name") != state.get("doctor_name"):
            extracted["doctor_id"] = None
        updates.update(extracted)
        merged = {**merged, **extracted}

        if merged.get("awaiting_patient_switch") or merged.get("awaiting_new_patient"):
            updates["confirmation"] = False
            merged["confirmation"] = False
        elif merged.get("awaiting_confirmation") and _truthy_yes(text):
            updates["confirmation"] = True
            merged["confirmation"] = True
        elif merged.get("awaiting_confirmation") and _truthy_no(text):
            updates["confirmation"] = False
            updates["awaiting_confirmation"] = False
            merged["confirmation"] = False
            merged["awaiting_confirmation"] = False

    ollama_decision = reason_with_ollama(merged)
    if ollama_decision:
        updates.update(ollama_decision)
        decision = ollama_decision
    else:
        decision = decide(merged)
        decision["reasoner"] = "planner"
        updates.update(decision)
    if decision.get("response"):
        updates["messages"] = [{"role": "assistant", "content": decision["response"]}]
    return updates


def run_tools(state: AgentState) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for call in state.get("pending_tool_calls") or []:
        name = str(call.get("name") or "")
        args = dict(call.get("args") or {})
        result = execute_tool_call(
            name,
            args,
            user_confirmed=state.get("confirmation") is True,
        )
        results.append({"name": name, "args": args, "result": result})

    updates: dict[str, Any] = {
        "pending_tool_calls": [],
        "last_tool_results": results,
        "messages": [{"role": "tool", "content": json.dumps(results, default=str)}],
    }
    for item in results:
        result = item["result"]
        data = result.get("data") or {}
        if item["name"] == "get_patient":
            if result.get("ok"):
                updates["patient_id"] = data.get("patient_id")
                updates["patient_name"] = data.get("name")
                updates["patient_verified"] = True
                updates["awaiting_new_patient"] = False
            else:
                updates["patient_verified"] = False
                if (result.get("error") or {}).get("code") == "PATIENT_NOT_FOUND":
                    lookup_name = str((item.get("args") or {}).get("name") or "").strip()
                    if lookup_name:
                        updates["patient_name"] = lookup_name
                        updates["awaiting_new_patient"] = True
            continue
        if item["name"] == "create_patient":
            if result.get("ok"):
                updates["patient_id"] = data.get("patient_id")
                updates["patient_name"] = data.get("name")
                updates["patient_verified"] = True
                updates["awaiting_new_patient"] = False
            continue
        if not result.get("ok"):
            continue
        if item["name"] == "check_availability":
            updates["doctor_id"] = data.get("doctor_id")
            updates["offered_slots"] = data.get("slots") or []
            doctor = data.get("doctor_id") or state.get("doctor_name") or ""
            updates["availability_fingerprint"] = (
                f"{doctor}|{state.get('date') or ''}|{state.get('time') or ''}"
            )
        elif item["name"] in {"book_appointment", "reschedule_appointment", "cancel_appointment"}:
            updates["appointment_id"] = data.get("appointment_id")
    return updates


def route_after_plan(state: AgentState) -> Any:
    if state.get("pending_tool_calls"):
        return "tools"
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", ingest_and_plan)
    graph.add_node("tools", run_tools)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", route_after_plan, {"tools": "tools", END: END})
    graph.add_edge("tools", "plan")
    return graph.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def run_turn(user_message: str, state: AgentState | None = None) -> AgentState:
    graph = get_graph()
    current: AgentState = dict(state or initial_state())
    current["pending_tool_calls"] = []
    current["messages"] = list(current.get("messages") or []) + [
        {"role": "user", "content": user_message},
    ]
    result = graph.invoke(current, {"recursion_limit": 12})
    return result
