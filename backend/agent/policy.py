"""Versioned appointment policies. Active version is selected from config, not hard-coded."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
ACTIVE_PATH = CONFIG_DIR / "active_policy.json"

DEFAULT_POLICY: dict[str, Any] = {
    "version": "v1",
    "require_confirmation_before_book": True,
    "require_confirmation_before_reschedule": True,
    "treat_book_as_confirmation": False,
    "resolve_relative_dates": True,
    "require_iso_date": False,
    "require_availability_check_before_mutation": True,
    "claim_success_only_from_tool": True,
}

_VERSION_RE = re.compile(r"^policy_v(\d+)\.json$")
_override: dict[str, Any] | None = None


def policy_path(version: str) -> Path:
    label = version if version.startswith("v") else f"v{version}"
    return CONFIG_DIR / f"policy_{label}.json"


def list_policy_versions() -> list[str]:
    versions: list[tuple[int, str]] = []
    if not CONFIG_DIR.exists():
        return ["v1"]
    for path in CONFIG_DIR.glob("policy_v*.json"):
        match = _VERSION_RE.match(path.name)
        if match:
            number = int(match.group(1))
            versions.append((number, f"v{number}"))
    if not versions:
        return ["v1"]
    versions.sort()
    return [label for _number, label in versions]


def next_policy_version() -> str:
    numbers = [int(item[1:]) for item in list_policy_versions()]
    return f"v{max(numbers, default=0) + 1}"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Policy file {path} must contain a JSON object.")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def active_version() -> str:
    if ACTIVE_PATH.exists():
        payload = _read_json(ACTIVE_PATH)
        return str(payload.get("version") or "v1")
    return "v1"


def activate_version(version: str) -> str:
    label = version if str(version).startswith("v") else f"v{version}"
    path = policy_path(label)
    if not path.exists():
        raise FileNotFoundError(f"Policy {label} does not exist at {path}")
    _write_json(ACTIVE_PATH, {"version": label})
    return label


def load_policy_file(version: str | None = None) -> dict[str, Any]:
    label = version or active_version()
    path = policy_path(label)
    merged = deepcopy(DEFAULT_POLICY)
    if path.exists():
        merged.update(_read_json(path))
    merged["version"] = label
    return merged


def get_policy() -> dict[str, Any]:
    if _override is not None:
        return deepcopy(_override)
    return load_policy_file()


def set_policy_override(policy: dict[str, Any] | None) -> None:
    global _override
    _override = deepcopy(policy) if policy is not None else None


def save_policy_version(policy: dict[str, Any], *, activate: bool = True) -> str:
    label = next_policy_version()
    stored = deepcopy(policy)
    stored["version"] = label
    _write_json(policy_path(label), stored)
    if activate:
        activate_version(label)
    return label


def current_policy_version() -> str:
    if _override is not None:
        return str(_override.get("version") or active_version())
    return active_version()
