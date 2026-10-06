from backend.tools import reschedule_appointment


def test_reschedule_without_confirmation_fails():
    result = reschedule_appointment(
        "APT-001",
        "PAT-001",
        "2026-10-07",
        "09:00",
        confirmed=False,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_reschedule_missing_slot_fails():
    result = reschedule_appointment(
        "APT-001",
        "PAT-001",
        "2026-10-06",
        "12:00",
        confirmed=True,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "SLOT_NOT_FOUND"


def test_successful_reschedule():
    result = reschedule_appointment(
        "APT-001",
        "PAT-001",
        "2026-10-07",
        "09:00",
        confirmed=True,
    )
    assert result["ok"] is True
    assert result["data"]["appointment_id"] == "APT-001"
    assert result["data"]["appointment_date"] == "2026-10-07"
    assert result["data"]["appointment_time"] == "09:00"
