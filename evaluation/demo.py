"""End-to-end demo: HTTP chat (or in-process fallback), SQLite proof, and evaluation.

Does not use an LLM judge. Optional Ollama is whatever the running API uses.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from backend.agent.sessions import clear_all_sessions, run_session_turn
from backend.database import get_connection
from backend.database.seed import seed_database
from evaluation.evaluator import evaluate_all

DEFAULT_API = "http://127.0.0.1:8000"


def _print(title: str, body: str = "") -> None:
    print(f"\n== {title} ==")
    if body:
        print(body)


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


class ChatClient:
    def __init__(self, base_url: str | None) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.mode = "http" if self.base_url else "in-process"

    def health(self) -> dict[str, Any] | None:
        if not self.base_url:
            return None
        return _request_json("GET", f"{self.base_url}/health")  # type: ignore[return-value]

    def chat(self, session_id: str, message: str) -> dict[str, Any]:
        if self.base_url:
            return _request_json(  # type: ignore[return-value]
                "POST",
                f"{self.base_url}/chat",
                {"session_id": session_id, "message": message},
            )
        state = run_session_turn(session_id, message)
        tools = [
            {
                "name": item.get("name"),
                "ok": (item.get("result") or {}).get("ok"),
            }
            for item in (state.get("last_tool_results") or [])
        ]
        return {
            "session_id": session_id,
            "response": state.get("response") or "",
            "tool_calls": tools,
            "status": state.get("status") or "ok",
        }

    def appointments(self) -> list[dict[str, Any]]:
        if self.base_url:
            return _request_json("GET", f"{self.base_url}/appointments")  # type: ignore[return-value]
        connection = get_connection()
        try:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT appointment_id, patient_id, doctor_id, appointment_date, appointment_time, status
                    FROM appointments
                    ORDER BY appointment_date, appointment_time
                    """
                ).fetchall()
            ]
        finally:
            connection.close()


def _has_appointment(rows: list[dict[str, Any]], appointment_id: str) -> bool:
    return any(row.get("appointment_id") == appointment_id and row.get("status") == "booked" for row in rows)


def _turn(client: ChatClient, session_id: str, message: str) -> dict[str, Any]:
    _print(f"{session_id} user", message)
    payload = client.chat(session_id, message)
    tools = ", ".join(
        f"{item.get('name')}(ok={item.get('ok')})"
        for item in (payload.get("tool_calls") or [])
        if item.get("name")
    )
    _print(
        "assistant",
        f"{payload.get('response')}\nstatus={payload.get('status')} tools={tools or 'none'}",
    )
    return payload


def _connect() -> ChatClient:
    base = os.getenv("DEMO_API", DEFAULT_API)
    client = ChatClient(base)
    try:
        health = client.health()
        _print("health", json.dumps(health, indent=2))
        return client
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _print("HTTP API unavailable", f"{base}: {exc}\nFalling back to in-process agent.")
        os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:9")
        return ChatClient(None)


def run_demo() -> int:
    failures: list[str] = []
    client = _connect()
    _print("mode", client.mode)

    if client.base_url:
        health = client.health() or {}
        db_path = health.get("database_path")
        if db_path:
            os.environ["DATABASE_PATH"] = str(db_path)
    seed_database(reset=True)
    clear_all_sessions()
    _print("database", "Reset clinic SQLite to seed rows (APT-001 only).")

    first = _turn(
        client,
        "demo-happy",
        "I need an appointment with Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.",
    )
    rows = client.appointments()
    if _has_appointment(rows, "APT-002"):
        failures.append("Booked APT-002 before the patient said yes.")
    if "book_appointment" in json.dumps(first.get("tool_calls") or []):
        failures.append("Called book_appointment on the unconfirmed turn.")

    _turn(client, "demo-happy", "Yes")
    rows = client.appointments()
    if not _has_appointment(rows, "APT-002"):
        failures.append("APT-002 was not persisted after confirmation.")
    _print("sqlite appointments after yes", json.dumps(rows, indent=2, default=str))

    refused = _turn(
        client,
        "demo-double",
        "Book me with Dr. Smith on 2026-10-06 at 10:00. I am PAT-003.",
    )
    if "APT-003" in (refused.get("response") or ""):
        failures.append("Invented or claimed APT-003 for an already-taken slot.")
    rows = client.appointments()
    booked_1000 = [
        row
        for row in rows
        if row.get("appointment_date") == "2026-10-06"
        and row.get("appointment_time") == "10:00"
        and row.get("status") == "booked"
    ]
    if len(booked_1000) != 1:
        failures.append(f"Expected one booked 10:00 row, found {len(booked_1000)}.")

    _turn(
        client,
        "demo-unavailable",
        "Book me with Dr. Smith on 2026-10-06 at 11:00. I am PAT-002.",
    )
    second_1100 = [
        row
        for row in client.appointments()
        if row.get("appointment_time") == "11:00"
        and row.get("patient_id") == "PAT-002"
        and row.get("status") == "booked"
    ]
    if second_1100:
        failures.append("Booked PAT-002 into the unavailable 11:00 slot.")

    report = evaluate_all()
    _print("evaluation", "\n".join(report.summary_lines()))
    if report.passed_count != len(report.results):
        failures.append(f"Evaluator passed {report.passed_count}/{len(report.results)}.")

    if failures:
        _print("DEMO FAILED", "\n".join(f"- {item}" for item in failures))
        return 1
    _print("DEMO PASSED", "Confirmation, SQLite persistence, double-booking refusal, and evaluator all succeeded.")
    return 0


def main() -> None:
    sys.exit(run_demo())


if __name__ == "__main__":
    main()
