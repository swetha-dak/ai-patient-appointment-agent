"""Turn failed evaluator checks into structured failure records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from evaluation.scoring import categorize


@dataclass(frozen=True)
class FailureRecord:
    failure_type: str
    scenario_id: str
    problem: str
    severity: str
    check_name: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _failure_type(check_name: str) -> str:
    if check_name == "confirmation_before_mutation" or check_name == "forbidden_tool:book_appointment":
        return "unsafe_booking"
    if check_name == "forbidden_tool:reschedule_appointment":
        return "unsafe_reschedule"
    if check_name.startswith("forbidden_tool:"):
        return "forbidden_tool_use"
    if check_name == "no_fake_success":
        return "fabricated_success"
    if check_name.startswith("db:"):
        return "incorrect_database_state"
    if check_name.startswith("tool:"):
        return "missing_or_incorrect_tool_call"
    if check_name == "reports_persisted_ids":
        return "unverified_success_claim"
    if check_name.startswith("ambiguity:"):
        return "ambiguous_slot_guess"
    if check_name.startswith("state:"):
        return "conversation_state_error"
    if check_name.startswith("quality:"):
        return "poor_conversation_quality"
    return "evaluation_check_failed"


def _severity(check_name: str) -> str:
    category = categorize(check_name)
    if check_name in {"confirmation_before_mutation", "no_fake_success"} or check_name.startswith("forbidden_tool"):
        return "critical"
    if category == "correctness" or check_name.startswith("db:"):
        return "high"
    if category in {"tools", "state", "ambiguity"}:
        return "medium"
    return "low"


def detect_failures(scenario_id: str, checks: Iterable[Any]) -> list[FailureRecord]:
    records: list[FailureRecord] = []
    for check in checks:
        if getattr(check, "passed", True):
            continue
        records.append(
            FailureRecord(
                failure_type=_failure_type(check.name),
                scenario_id=scenario_id,
                problem=f"{check.name}: {check.detail}",
                severity=_severity(check.name),
                check_name=check.name,
            )
        )
    return records
