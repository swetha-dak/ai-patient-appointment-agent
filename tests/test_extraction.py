from datetime import date

from backend.agent.extraction import extract_from_message, parse_time_text, resolve_date_text
from backend.agent.sessions import run_session_turn


def test_resolve_next_tuesday_in_python():
    today = date(2026, 10, 6)  # Tuesday
    iso, relative = resolve_date_text("I want to see Dr. Smith next Tuesday morning.", today=today)
    assert iso == "2026-10-13"
    assert relative is True


def test_resolve_october_6_in_python():
    iso, relative = resolve_date_text("I want October 6 at 10 AM.", today=date(2026, 10, 1))
    assert iso == "2026-10-06"
    assert parse_time_text("I want October 6 at 10 AM.") == "10:00"


def test_does_not_guess_sometime_next_week():
    iso, _relative = resolve_date_text(
        "I want an appointment with Dr. Smith sometime next week. I am PAT-003.",
        today=date(2026, 10, 6),
    )
    assert iso is None


def test_see_doctor_sets_book_intent_without_appointment_keyword():
    updates = extract_from_message("I want to see Dr. Smith next Tuesday morning.")
    assert updates.get("appointment_intent") == "book"
    assert updates.get("doctor_name") == "Dr. Smith"
    assert updates.get("patient_id") is None
    assert "time" not in updates or updates.get("time") is None


def test_october_phrase_then_confirmation_still_uses_tools():
    first = run_session_turn("nlu-oct", "I need an appointment with Dr. Smith.")
    assert first.get("patient_id") is None
    identified = run_session_turn("nlu-oct", "My patient ID is PAT-002.")
    assert identified.get("patient_id") == "PAT-002"
    assert identified.get("patient_verified") is True
    asked = run_session_turn("nlu-oct", "I want 2026-10-06 at 10 AM.")
    tools = [item["name"] for item in (asked.get("last_tool_results") or [])]
    assert "check_availability" in tools
    assert "book_appointment" not in tools
    assert asked.get("awaiting_confirmation") is True
    booked = run_session_turn("nlu-oct", "Yes, book it.")
    assert booked.get("appointment_id") == "APT-002"
    other = run_session_turn("nlu-oct-other", "I need an appointment with Dr. Smith.")
    assert other.get("patient_id") is None
