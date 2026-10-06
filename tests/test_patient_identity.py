from backend.agent import initial_state, session_snapshot
from backend.agent.sessions import run_session_turn


def test_new_session_asks_for_patient_identity():
    state = run_session_turn("id-session-a", "I need an appointment with Dr. Smith.")
    assert state.get("patient_id") is None
    assert state.get("patient_verified") is not True
    assert "patient" in (state.get("response") or "").lower()
    tools = [item["name"] for item in (state.get("last_tool_results") or [])]
    assert "book_appointment" not in tools
    assert "get_patient" not in tools


def test_explicit_patient_is_stored_on_current_session_only():
    first = run_session_turn("id-session-a", "I need an appointment with Dr. Smith.")
    assert first.get("patient_id") is None
    identified = run_session_turn("id-session-a", "I am PAT-002.")
    assert identified.get("patient_id") == "PAT-002"
    assert identified.get("patient_verified") is True
    snap = session_snapshot("id-session-a")
    assert snap["patient_id"] == "PAT-002"

    other = run_session_turn("id-session-b", "I need an appointment with Dr. Smith.")
    assert other.get("patient_id") is None
    assert other.get("patient_verified") is not True
    assert session_snapshot("id-session-b")["patient_id"] is None


def test_booking_after_identity_still_requires_confirmation():
    run_session_turn("id-session-book", "I need an appointment with Dr. Smith on 2026-10-06 at 10:00.")
    run_session_turn("id-session-book", "I am PAT-002.")
    asked = run_session_turn(
        "id-session-book",
        "Please book Dr. Smith on 2026-10-06 at 10:00.",
    )
    assert asked.get("patient_id") == "PAT-002"
    assert asked.get("awaiting_confirmation") is True
    tools = [item["name"] for item in (asked.get("last_tool_results") or [])]
    assert "book_appointment" not in tools
    booked = run_session_turn("id-session-book", "Yes")
    assert booked.get("appointment_id") == "APT-002"


def test_lowercase_full_name_is_verified():
    run_session_turn("id-name-case", "I need an appointment with Dr. Smith.")
    identified = run_session_turn("id-name-case", "my name is brian cole")
    assert identified.get("patient_id") == "PAT-002"
    assert identified.get("patient_verified") is True


def test_name_after_identity_prompt_looks_up_sqlite():
    run_session_turn("id-name-prompt", "I need an appointment with Dr. Smith.")
    missing = run_session_turn("id-name-prompt", "madhumitha")
    assert missing.get("patient_verified") is not True
    assert "not in the clinic" in (missing.get("response") or "").lower()
    tools = [item["name"] for item in (missing.get("last_tool_results") or [])]
    assert "get_patient" in tools
    assert "book_appointment" not in tools
    found = run_session_turn("id-name-prompt", "brian")
    assert found.get("patient_id") == "PAT-002"
    assert found.get("patient_verified") is True


def test_unknown_name_registers_then_books():
    run_session_turn("id-new-patient", "I need an appointment with Dr. Smith on 2026-10-06 at 10:00.")
    missing = run_session_turn("id-new-patient", "Kajal agarwal")
    assert missing.get("patient_verified") is not True
    assert missing.get("awaiting_new_patient") is True
    assert "not in the clinic" in (missing.get("response") or "").lower()
    created = run_session_turn("id-new-patient", "1990-05-15 555-010-9999")
    assert created.get("patient_id") == "PAT-005"
    assert created.get("patient_verified") is True
    assert created.get("awaiting_new_patient") is False
    assert created.get("awaiting_confirmation") is True
    booked = run_session_turn("id-new-patient", "Yes")
    assert booked.get("appointment_id")
    tools = [item["name"] for item in (booked.get("last_tool_results") or [])]
    assert "book_appointment" in tools


def test_unknown_patient_id_does_not_auto_create():
    run_session_turn("id-unknown-pat", "I need an appointment with Dr. Smith.")
    missing = run_session_turn("id-unknown-pat", "I am PAT-999.")
    assert missing.get("patient_verified") is not True
    assert missing.get("awaiting_new_patient") is not True
    tools = [item["name"] for item in (missing.get("last_tool_results") or [])]
    assert "create_patient" not in tools

    run_session_turn("id-session-switch", "I am PAT-002. I need an appointment with Dr. Smith.")
    switched = run_session_turn("id-session-switch", "Actually I am PAT-003.")
    assert switched.get("patient_id") == "PAT-002"
    assert switched.get("awaiting_patient_switch") is True
    assert "PAT-003" in (switched.get("response") or "")
    confirmed = run_session_turn("id-session-switch", "Yes")
    assert confirmed.get("patient_id") == "PAT-003"
    assert confirmed.get("patient_verified") is True
