from backend.tools import cancel_appointment


def test_cancel_wrong_patient_fails():
    result = cancel_appointment("APT-001", "PAT-002")
    assert result["ok"] is False
    assert result["error"]["code"] == "APPOINTMENT_MISMATCH"


def test_cancel_own_appointment():
    result = cancel_appointment("APT-001", "PAT-001")
    assert result["ok"] is True
    assert result["data"]["status"] == "cancelled"
