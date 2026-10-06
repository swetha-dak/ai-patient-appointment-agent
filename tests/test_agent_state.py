from backend.agent import initial_state, run_turn, session_snapshot
from backend.agent.sessions import run_session_turn


def test_agent_asks_confirmation_before_booking():
    state = run_turn(
        "I need an appointment with Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.",
        initial_state("test-agent"),
    )
    assert state.get("awaiting_confirmation") is True
    assert state.get("confirmation") is False
    tools = [item["name"] for item in (state.get("last_tool_results") or [])]
    assert "book_appointment" not in tools
    assert "APT-002" not in (state.get("response") or "")


def test_session_state_persists_across_turns():
    first = run_session_turn(
        "test-session",
        "I need an appointment with Dr. Smith on 2026-10-06 at 10:00. I am PAT-002.",
    )
    snap = session_snapshot("test-session")
    assert snap["patient_id"] == "PAT-002"
    assert snap["date"] == "2026-10-06"
    assert snap["time"] == "10:00"
    assert snap["awaiting_confirmation"] is True
    assert first.get("appointment_id") != "APT-002"
    second = run_session_turn("test-session", "Yes")
    assert second.get("appointment_id") == "APT-002"
    assert "APT-002" in (second.get("response") or "")
