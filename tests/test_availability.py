from backend.tools import check_availability


def test_check_availability_returns_sqlite_slots_only():
    result = check_availability(doctor_id="DOC-001", appointment_date="2026-10-06")
    assert result["ok"] is True
    times = [slot["appointment_time"] for slot in result["data"]["slots"]]
    assert "09:00" in times
    assert "10:00" in times
    assert "11:00" not in times


def test_unknown_slot_is_not_invented():
    result = check_availability(
        doctor_id="DOC-001",
        appointment_date="2026-10-06",
        appointment_time="12:00",
    )
    assert result["ok"] is True
    assert result["data"]["slots"] == []
