"""FastAPI routes for chat, clinic reads, and evaluation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.agent.policy import current_policy_version, get_policy, list_policy_versions
from backend.agent.sessions import run_session_turn
from backend.agent.settings import ollama_base_url, ollama_model
from backend.database import get_connection, get_database_path
from backend.models.schemas import (
    ChatRequest,
    ChatResponse,
    EvaluateRequest,
    HealthResponse,
    ImproveRequest,
    ToolCallOut,
)
from evaluation.evaluator import evaluate_all
from evaluation.improvement import run_improvement_cycle

router = APIRouter()


def _rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    connection = get_connection()
    try:
        return [dict(row) for row in connection.execute(query, params).fetchall()]
    finally:
        connection.close()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="appointment-agent",
        phase=19,
        database_path=str(get_database_path()),
        ollama_base_url=ollama_base_url(),
        ollama_model=ollama_model(),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    message = body.message.strip()
    session_id = body.session_id.strip()
    if not session_id or not message:
        raise HTTPException(status_code=400, detail="session_id and message are required.")
    state = run_session_turn(session_id, message)
    tool_calls = [
        ToolCallOut(
            name=str(item.get("name") or ""),
            args=dict(item.get("args") or {}),
            ok=(item.get("result") or {}).get("ok"),
        )
        for item in (state.get("last_tool_results") or [])
    ]
    agent_status = str(state.get("status") or "ok")
    status = "success" if agent_status in {"ok", "success"} else agent_status
    return ChatResponse(
        session_id=session_id,
        response=str(state.get("response") or ""),
        tool_calls=tool_calls,
        status=status,
    )


@router.post("/evaluate")
def evaluate(body: EvaluateRequest = EvaluateRequest()) -> dict[str, Any]:
    report = evaluate_all(body.scenario_ids)
    return {
        "status": "success",
        "summary": report.summary_lines(),
        **report.as_dict(),
    }


@router.get("/policy")
def policy() -> dict[str, Any]:
    return {
        "active_version": current_policy_version(),
        "versions": list_policy_versions(),
        "policy": get_policy(),
    }


@router.post("/improve")
def improve(body: ImproveRequest = ImproveRequest()) -> dict[str, Any]:
    return run_improvement_cycle(body.scenario_ids)


@router.get("/doctors")
def list_doctors() -> list[dict[str, Any]]:
    return _rows("SELECT doctor_id, name, specialty FROM doctors ORDER BY doctor_id")


@router.get("/appointments")
def list_appointments() -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT appointment_id, patient_id, doctor_id, appointment_date, appointment_time, status
        FROM appointments
        ORDER BY appointment_date, appointment_time
        """
    )


@router.get("/availability")
def list_availability(
    doctor_id: str | None = Query(default=None),
    appointment_date: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    query = """
        SELECT availability_id, doctor_id, appointment_date, appointment_time, is_available
        FROM availability
        WHERE 1=1
    """
    params: list[str] = []
    if doctor_id:
        query += " AND doctor_id = ?"
        params.append(doctor_id)
    if appointment_date:
        query += " AND appointment_date = ?"
        params.append(appointment_date)
    query += " ORDER BY appointment_date, appointment_time"
    rows = _rows(query, tuple(params))
    for row in rows:
        row["is_available"] = bool(row["is_available"])
    return rows
