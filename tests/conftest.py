import pytest

from backend.agent.policy import set_policy_override
from backend.agent.sessions import clear_all_sessions
from backend.database.seed import seed_database


@pytest.fixture(autouse=True)
def isolated_clinic(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "clinic.db"))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "1")
    set_policy_override(None)
    clear_all_sessions()
    seed_database(reset=True)
    yield
    set_policy_override(None)
    clear_all_sessions()
