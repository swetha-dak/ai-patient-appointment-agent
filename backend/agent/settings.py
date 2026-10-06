"""Environment configuration. Model name is not hard-coded in agent logic."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:3b"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 120


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)


def ollama_timeout_seconds() -> int:
    raw = os.getenv("OLLAMA_TIMEOUT_SECONDS", str(DEFAULT_OLLAMA_TIMEOUT_SECONDS))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_OLLAMA_TIMEOUT_SECONDS
