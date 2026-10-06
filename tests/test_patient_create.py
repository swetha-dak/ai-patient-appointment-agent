from backend.tools import create_patient, get_patient


def test_create_patient_inserts_next_id():
    created = create_patient("Kajal agarwal", "1990-05-15", "555-010-9999")
    assert created["ok"] is True
    assert created["data"]["patient_id"] == "PAT-005"
    assert created["data"]["name"] == "Kajal Agarwal"
    assert created["data"]["phone"] == "5550109999"
    found = get_patient(name="kajal agarwal")
    assert found["ok"] is True
    assert found["data"]["patient_id"] == "PAT-005"


def test_create_patient_reuses_existing_name():
    first = create_patient("Brian Cole", "1991-03-22", "5550001111")
    assert first["ok"] is True
    assert first["data"]["patient_id"] == "PAT-002"


def test_create_patient_rejects_short_phone():
    result = create_patient("New Person", "1990-01-01", "123")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"
