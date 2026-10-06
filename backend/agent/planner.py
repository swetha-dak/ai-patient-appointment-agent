"""Deterministic planner used as the LangGraph reasoner until Ollama is wired."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from backend.agent.policy import get_policy
from backend.agent.state import AgentState
from backend.tools.common import open_connection

PATIENT_ID_RE = re.compile(r"\bPAT-\d+\b", re.I)
DOCTOR_ID_RE = re.compile(r"\bDOC-\d+\b", re.I)
APPOINTMENT_ID_RE = re.compile(r"\bAPT-\d+\b", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
DOCTOR_NAME_RE = re.compile(r"\bdr\.?\s+([A-Za-z]+)\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
TIME_24_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
NAME_RE = re.compile(
    r"\b(?:i am|i'm|this is|my name is)\s+(?!pat-\d)([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*)*)",
    re.I,
)
YES_RE = re.compile(r"^\s*(yes|yeah|yep|y|ok|okay)\b", re.I)
NO_RE = re.compile(r"^\s*(no|nope|n)\b", re.I)


def _normalize_time(hour: int, minute: int, meridian: str | None) -> str | None:
    if meridian:
        meridian = meridian.lower()
        if meridian == "pm" and hour < 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def extract_from_message(text: str) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    lowered = text.lower()

    if re.search(r"\bcancel", lowered):
        updates["appointment_intent"] = "cancel"
    elif re.search(r"\breschedul|\bchange (my )?appointment|\bmove (my )?appointment", lowered):
        updates["appointment_intent"] = "reschedule"
    elif re.search(r"\bbook|\bappointment|\bschedule|\bavailable|\bslot", lowered):
        updates["appointment_intent"] = "book"

    patient_id = PATIENT_ID_RE.search(text)
    if patient_id:
        updates["patient_id"] = patient_id.group(0).upper()
    doctor_id = DOCTOR_ID_RE.search(text)
    if doctor_id:
        updates["doctor_id"] = doctor_id.group(0).upper()
    appointment_id = APPOINTMENT_ID_RE.search(text)
    if appointment_id:
        updates["appointment_id"] = appointment_id.group(0).upper()

    doctor_name = DOCTOR_NAME_RE.search(text)
    if doctor_name:
        updates["doctor_name"] = f"Dr. {doctor_name.group(1).title()}"

    patient_name = NAME_RE.search(text)
    if patient_name:
        updates["patient_name"] = patient_name.group(1).strip()

    iso_date = ISO_DATE_RE.search(text)
    if iso_date:
        updates["date"] = iso_date.group(1)
        updates["date_is_relative"] = False
    else:
        policy = get_policy()
        if policy.get("resolve_relative_dates") and not policy.get("require_iso_date"):
            if re.search(r"\btoday\b", lowered):
                updates["date"] = date.today().isoformat()
                updates["date_is_relative"] = True
            elif re.search(r"\btomorrow\b", lowered):
                updates["date"] = (date.today() + timedelta(days=1)).isoformat()
                updates["date_is_relative"] = True

    ampm = TIME_RE.search(text)
    if ampm:
        normalized = _normalize_time(int(ampm.group(1)), int(ampm.group(2) or 0), ampm.group(3))
        if normalized:
            updates["time"] = normalized
    else:
        time_24 = TIME_24_RE.search(text)
        if time_24:
            updates["time"] = f"{int(time_24.group(1)):02d}:{time_24.group(2)}"

    return updates


def _doctor_for_appointment(appointment_id: str) -> str | None:
    connection = open_connection()
    try:
        row = connection.execute(
            "SELECT doctor_id FROM appointments WHERE appointment_id = ?",
            (appointment_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row["doctor_id"])
    finally:
        connection.close()


def _fingerprint(state: AgentState) -> str:
    doctor = state.get("doctor_id") or state.get("doctor_name") or ""
    return f"{doctor}|{state.get('date') or ''}|{state.get('time') or ''}"


def _slot_matches(state: AgentState) -> bool:
    wanted_time = state.get("time")
    wanted_date = state.get("date")
    for slot in state.get("offered_slots") or []:
        if wanted_time and slot.get("appointment_time") != wanted_time:
            continue
        if wanted_date and slot.get("appointment_date") != wanted_date:
            continue
        if slot.get("is_available") is False:
            continue
        return True
    return False


def _format_slots(slots: list[dict[str, Any]]) -> str:
    if not slots:
        return "none"
    return ", ".join(
        f"{slot.get('appointment_date')} {slot.get('appointment_time')}"
        for slot in slots
        if slot.get("is_available", True)
    )


def _last_tool(state: AgentState) -> dict[str, Any] | None:
    results = state.get("last_tool_results") or []
    if not results:
        return None
    return results[-1]


def decide(state: AgentState) -> dict[str, Any]:
    last = _last_tool(state)
    if last:
        result = last.get("result") or {}
        name = last.get("name")
        if name == "create_patient":
            if result.get("ok"):
                data = result["data"]
                verified = {
                    "awaiting_new_patient": False,
                    "patient_verified": True,
                    "patient_id": data.get("patient_id"),
                    "patient_name": data.get("name"),
                    "status": "ok",
                }
                if (
                    (state.get("appointment_intent") or "unknown") == "book"
                    and (state.get("doctor_id") or state.get("doctor_name"))
                    and state.get("date")
                ):
                    args: dict[str, Any] = {"appointment_date": state["date"]}
                    if state.get("doctor_id"):
                        args["doctor_id"] = state["doctor_id"]
                    else:
                        args["doctor_name"] = state["doctor_name"]
                    if state.get("time"):
                        args["appointment_time"] = state["time"]
                    return {**verified, "pending_tool_calls": [{"name": "check_availability", "args": args}]}
                return {
                    **verified,
                    "pending_tool_calls": [],
                    "response": (
                        f"Created patient {data.get('patient_id')} ({data.get('name')}) in the clinic records. "
                        "We can continue booking."
                    ),
                }
            error = result.get("error") or {}
            return {
                "pending_tool_calls": [],
                "status": "error",
                "response": error.get("message", "Could not create the patient record."),
            }
        if name in {"book_appointment", "cancel_appointment", "reschedule_appointment"}:
            if result.get("ok"):
                data = result["data"]
                action = "Booked" if name == "book_appointment" else (
                    "Cancelled" if name == "cancel_appointment" else "Rescheduled"
                )
                return {
                    "pending_tool_calls": [],
                    "status": "success",
                    "awaiting_confirmation": False,
                    "confirmation": False,
                    "response": (
                        f"{action} appointment {data.get('appointment_id')} on "
                        f"{data.get('appointment_date')} at {data.get('appointment_time')} "
                        f"(status={data.get('status')})."
                    ),
                }
            error = result.get("error") or {}
            return {
                "pending_tool_calls": [],
                "status": "error",
                "awaiting_confirmation": False,
                "confirmation": False,
                "response": error.get("message", "The database operation failed."),
            }
        if not result.get("ok"):
            error = result.get("error") or {}
            lookup_name = str((last.get("args") or {}).get("name") or state.get("patient_name") or "").strip()
            if name == "get_patient" and (error.get("code") == "PATIENT_NOT_FOUND") and lookup_name:
                return {
                    "pending_tool_calls": [],
                    "awaiting_new_patient": True,
                    "patient_name": lookup_name,
                    "patient_verified": False,
                    "response": (
                        f"{lookup_name} is not in the clinic records. I can create a new patient file. "
                        "Please send date of birth as YYYY-MM-DD and a phone number."
                    ),
                    "status": "ok",
                }
            return {
                "pending_tool_calls": [],
                "status": "error",
                "response": error.get("message", "A tool call failed."),
            }

    if state.get("awaiting_patient_switch"):
        current = state.get("patient_id") or state.get("patient_name") or "the current patient"
        pending = state.get("pending_patient_id") or state.get("pending_patient_name") or "the new patient"
        return {
            "pending_tool_calls": [],
            "response": (
                f"This session is already identified as {current}. "
                f"Do you want to switch to {pending}? Please say yes or no."
            ),
            "status": "ok",
        }

    intent = state.get("appointment_intent") or "unknown"
    if intent == "unknown":
        return {
            "pending_tool_calls": [],
            "response": "I can book, cancel, or reschedule an appointment. What would you like to do?",
            "status": "ok",
        }

    if not state.get("patient_verified"):
        if state.get("awaiting_new_patient") and state.get("patient_name"):
            if not state.get("patient_dob"):
                return {
                    "pending_tool_calls": [],
                    "awaiting_new_patient": True,
                    "response": "Please send the date of birth as YYYY-MM-DD.",
                    "status": "ok",
                }
            if not state.get("patient_phone"):
                return {
                    "pending_tool_calls": [],
                    "awaiting_new_patient": True,
                    "response": "Please send a phone number with at least 7 digits.",
                    "status": "ok",
                }
            return {
                "pending_tool_calls": [
                    {
                        "name": "create_patient",
                        "args": {
                            "name": state["patient_name"],
                            "date_of_birth": state["patient_dob"],
                            "phone": state["patient_phone"],
                        },
                    }
                ]
            }
        if state.get("patient_id"):
            return {
                "pending_tool_calls": [
                    {"name": "get_patient", "args": {"patient_id": state["patient_id"]}},
                ]
            }
        if state.get("patient_name"):
            return {
                "pending_tool_calls": [
                    {"name": "get_patient", "args": {"name": state["patient_name"]}},
                ]
            }
        return {
            "pending_tool_calls": [],
            "response": "Please provide your patient ID or full name.",
            "status": "ok",
        }

    if intent == "cancel":
        if not state.get("appointment_id"):
            return {
                "pending_tool_calls": [],
                "response": "Which appointment ID should I cancel?",
                "status": "ok",
            }
        return {
            "pending_tool_calls": [
                {
                    "name": "cancel_appointment",
                    "args": {
                        "appointment_id": state["appointment_id"],
                        "patient_id": state["patient_id"],
                    },
                }
            ]
        }

    if intent == "reschedule":
        if not state.get("appointment_id"):
            return {
                "pending_tool_calls": [],
                "response": "Which appointment ID should I reschedule?",
                "status": "ok",
            }
        if not state.get("date") or not state.get("time"):
            return {
                "pending_tool_calls": [],
                "response": "What new date and time should I use? Please use YYYY-MM-DD and HH:MM.",
                "status": "ok",
            }
        if not state.get("doctor_id"):
            doctor_id = _doctor_for_appointment(str(state["appointment_id"]))
            if not doctor_id:
                return {
                    "pending_tool_calls": [],
                    "status": "error",
                    "response": "That appointment id was not found in the clinic database.",
                }
            state = {**state, "doctor_id": doctor_id}

    if not state.get("doctor_id") and not state.get("doctor_name"):
        return {
            "pending_tool_calls": [],
            "response": "Which doctor would you like to see?",
            "status": "ok",
        }
    if not state.get("date"):
        return {
            "pending_tool_calls": [],
            "response": "What date would you prefer? Please use YYYY-MM-DD.",
            "status": "ok",
        }
    policy = get_policy()
    if policy.get("require_iso_date") and state.get("date_is_relative"):
        return {
            "pending_tool_calls": [],
            "date": None,
            "date_is_relative": False,
            "response": "That date is ambiguous. Please provide a calendar date as YYYY-MM-DD.",
            "status": "ok",
        }

    fp = _fingerprint(state)
    needs_availability = state.get("availability_fingerprint") != fp
    if needs_availability:
        args: dict[str, Any] = {"appointment_date": state["date"]}
        if state.get("doctor_id"):
            args["doctor_id"] = state["doctor_id"]
        else:
            args["doctor_name"] = state["doctor_name"]
        if state.get("time"):
            args["appointment_time"] = state["time"]
        update: dict[str, Any] = {"pending_tool_calls": [{"name": "check_availability", "args": args}]}
        if state.get("doctor_id"):
            update["doctor_id"] = state["doctor_id"]
        return update

    slots = state.get("offered_slots") or []
    if not slots:
        return {
            "pending_tool_calls": [],
            "response": "There are no available slots for that request in the clinic schedule.",
            "status": "ok",
        }

    if not state.get("time"):
        return {
            "pending_tool_calls": [],
            "response": f"Available slots: {_format_slots(slots)}. Which time would you like?",
            "status": "ok",
        }

    if not _slot_matches(state):
        return {
            "pending_tool_calls": [],
            "response": (
                "That slot is not available. "
                f"Available slots: {_format_slots(slots)}."
            ),
            "status": "ok",
        }

    if not state.get("confirmation"):
        policy = get_policy()
        needs_confirm = (
            (intent != "reschedule" and policy.get("require_confirmation_before_book", True))
            or (intent == "reschedule" and policy.get("require_confirmation_before_reschedule", True))
        )
        if needs_confirm and not policy.get("treat_book_as_confirmation"):
            doctor_label = state.get("doctor_name") or state.get("doctor_id")
            return {
                "pending_tool_calls": [],
                "awaiting_confirmation": True,
                "confirmation": False,
                "response": (
                    f"{state.get('time')} on {state.get('date')} is available with {doctor_label}. "
                    "Would you like me to book it?"
                ),
                "status": "ok",
            }

    if not state.get("doctor_id"):
        return {
            "pending_tool_calls": [],
            "response": "I still need a doctor ID from availability before booking.",
            "status": "error",
        }

    mutating_tool = "book_appointment"
    args = {
        "patient_id": state["patient_id"],
        "doctor_id": state["doctor_id"],
        "appointment_date": state["date"],
        "appointment_time": state["time"],
        "confirmed": True,
    }
    if intent == "reschedule":
        if not state.get("appointment_id"):
            return {
                "pending_tool_calls": [],
                "awaiting_confirmation": False,
                "confirmation": False,
                "response": "Which appointment ID should I reschedule?",
                "status": "ok",
            }
        mutating_tool = "reschedule_appointment"
        args = {
            "appointment_id": state["appointment_id"],
            "patient_id": state["patient_id"],
            "appointment_date": state["date"],
            "appointment_time": state["time"],
            "doctor_id": state.get("doctor_id"),
            "confirmed": True,
        }

    return {"pending_tool_calls": [{"name": mutating_tool, "args": args}]}
