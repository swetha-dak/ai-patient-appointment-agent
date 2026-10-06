"""Execute appointment tools requested by the LangGraph agent."""

from __future__ import annotations

from typing import Any, Callable

from backend.tools import (
    book_appointment,
    cancel_appointment,
    check_availability,
    create_patient,
    get_patient,
    reschedule_appointment,
)

TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_patient": get_patient,
    "create_patient": create_patient,
    "check_availability": check_availability,
    "book_appointment": book_appointment,
    "cancel_appointment": cancel_appointment,
    "reschedule_appointment": reschedule_appointment,
}


MUTATING_TOOLS = {"book_appointment", "reschedule_appointment"}


def execute_tool_call(
    name: str,
    args: dict[str, Any] | None,
    *,
    user_confirmed: bool = False,
) -> dict[str, Any]:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {
            "ok": False,
            "error": {"code": "UNKNOWN_TOOL", "message": f"No tool named {name}."},
            "data": None,
        }
    payload = dict(args or {})
    if name in MUTATING_TOOLS:
        payload["confirmed"] = user_confirmed is True
    try:
        return function(**payload)
    except TypeError as exc:
        return {
            "ok": False,
            "error": {"code": "INVALID_TOOL_ARGS", "message": str(exc)},
            "data": None,
        }
