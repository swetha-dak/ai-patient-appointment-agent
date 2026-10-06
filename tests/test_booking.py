from backend.tools import book_appointment


def test_booking_without_confirmation_fails():
    result = book_appointment("PAT-002", "DOC-001", "2026-10-06", "10:00", confirmed=False)
    assert result["ok"] is False
    assert result["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_booking_unavailable_slot_fails():
    result = book_appointment("PAT-002", "DOC-001", "2026-10-06", "11:00", confirmed=True)
    assert result["ok"] is False
    assert result["error"]["code"] == "SLOT_UNAVAILABLE"


def test_successful_booking():
    result = book_appointment("PAT-002", "DOC-001", "2026-10-06", "10:00", confirmed=True)
    assert result["ok"] is True
    assert result["data"]["appointment_id"] == "APT-002"
    assert result["data"]["status"] == "booked"


def test_double_booking_fails():
    first = book_appointment("PAT-002", "DOC-001", "2026-10-06", "10:00", confirmed=True)
    assert first["ok"] is True
    second = book_appointment("PAT-003", "DOC-001", "2026-10-06", "10:00", confirmed=True)
    assert second["ok"] is False
    assert second["error"]["code"] in {"SLOT_UNAVAILABLE", "DOUBLE_BOOKING"}
