"""Generate policy patches from structured failures. Does not retrain the LLM."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.agent.policy import get_policy, save_policy_version, set_policy_override
from evaluation.evaluator import EvaluationReport, evaluate_all
from evaluation.failures import FailureRecord
from evaluation.regression import compare_reports

IMPROVEMENTS_PATH = Path(__file__).resolve().parents[1] / "config" / "improvements.json"

PATCH_BY_FAILURE: dict[str, dict[str, Any]] = {
    "unsafe_booking": {
        "require_confirmation_before_book": True,
        "treat_book_as_confirmation": False,
    },
    "unsafe_reschedule": {
        "require_confirmation_before_reschedule": True,
        "treat_book_as_confirmation": False,
    },
    "ambiguous_slot_guess": {
        "require_iso_date": True,
        "resolve_relative_dates": False,
    },
    "fabricated_success": {
        "claim_success_only_from_tool": True,
    },
    "incorrect_database_state": {
        "require_availability_check_before_mutation": True,
    },
    "unverified_success_claim": {
        "claim_success_only_from_tool": True,
    },
}


@dataclass
class Improvement:
    improvement_id: str
    failure_type: str
    scenario_id: str
    patch: dict[str, Any]
    problem: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_improvements(failures: list[FailureRecord]) -> list[Improvement]:
    improvements: list[Improvement] = []
    seen: set[tuple[str, str]] = set()
    for index, failure in enumerate(failures, start=1):
        patch = PATCH_BY_FAILURE.get(failure.failure_type)
        if not patch:
            continue
        key = (failure.failure_type, failure.scenario_id)
        if key in seen:
            continue
        seen.add(key)
        improvements.append(
            Improvement(
                improvement_id=f"IMP-{index:03d}",
                failure_type=failure.failure_type,
                scenario_id=failure.scenario_id,
                patch=dict(patch),
                problem=failure.problem,
            )
        )
    return improvements


def apply_improvements(base_policy: dict[str, Any], improvements: list[Improvement]) -> dict[str, Any]:
    candidate = deepcopy(base_policy)
    for improvement in improvements:
        candidate.update(improvement.patch)
    return candidate


def run_improvement_cycle(scenario_ids: list[str] | None = None) -> dict[str, Any]:
    version_before = str(get_policy().get("version") or "v1")
    before = evaluate_all(scenario_ids)
    failures = [failure for result in before.results for failure in result.failures]
    if not failures:
        return {
            "accepted": False,
            "reason": "No evaluation failures to improve.",
            "policy_version_before": version_before,
            "policy_version_after": version_before,
            "before_score": before.as_dict()["overall_score"],
            "after_score": before.as_dict()["overall_score"],
            "improvements": [],
            "regression": compare_reports(before, before).as_dict(),
            "before": before.as_dict(),
            "after": before.as_dict(),
        }

    improvements = generate_improvements(failures)
    if not improvements:
        return {
            "accepted": False,
            "reason": "Failures exist but no policy patch is defined for those failure types.",
            "before_score": before.as_dict()["overall_score"],
            "after_score": before.as_dict()["overall_score"],
            "improvements": [],
            "failures": [failure.as_dict() for failure in failures],
            "before": before.as_dict(),
        }

    candidate = apply_improvements(get_policy(), improvements)
    set_policy_override(candidate)
    try:
        after = evaluate_all(scenario_ids)
    finally:
        set_policy_override(None)

    regression = compare_reports(before, after)
    accepted = regression.target_fixed and regression.passed
    if accepted:
        reason = "Accepted."
    elif not regression.target_fixed:
        reason = "Rejected: target failure was not fixed."
    elif regression.regressions:
        reason = f"Rejected: regression in {', '.join(regression.regressions)}."
    else:
        reason = "Rejected: critical safety regression."
    if accepted:
        saved_version = save_policy_version(candidate, activate=True)
        set_policy_override(None)
    else:
        saved_version = None

    record = {
        "accepted": accepted,
        "reason": reason,
        "policy_version_before": version_before,
        "policy_version_after": saved_version or version_before,
        "before_score": before.as_dict()["overall_score"],
        "after_score": after.as_dict()["overall_score"],
        "regression": regression.as_dict(),
        "improvements": [item.as_dict() for item in improvements],
        "failures": [failure.as_dict() for failure in failures],
        "candidate_policy": candidate,
        "before": {"passed": before.passed_count, "total": len(before.results), "overall_score": before.as_dict()["overall_score"]},
        "after": {"passed": after.passed_count, "total": len(after.results), "overall_score": after.as_dict()["overall_score"]},
    }
    IMPROVEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    history: list[dict[str, Any]] = []
    if IMPROVEMENTS_PATH.exists():
        history = json.loads(IMPROVEMENTS_PATH.read_text(encoding="utf-8") or "[]")
        if not isinstance(history, list):
            history = []
    history.append(record)
    IMPROVEMENTS_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return record


def main() -> None:
    result = run_improvement_cycle()
    print(f"accepted={result['accepted']}")
    print(result["reason"])
    print(f"before={result['before_score']}% after={result['after_score']}%")
    if result.get("regression"):
        print(f"Regression: {result['regression'].get('regression_count', 0)}")
    for item in result.get("improvements") or []:
        print(f"{item['improvement_id']} {item['failure_type']} -> {item['patch']}")


if __name__ == "__main__":
    main()
