"""Compare two evaluation reports for regressions. No LLM judge."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from evaluation.evaluator import EvaluationReport
from evaluation.failures import FailureRecord


@dataclass
class RegressionReport:
    still_passing: list[str]
    still_failing: list[str]
    newly_passing: list[str]
    regressions: list[str]
    critical_safety_regressions: list[dict[str, Any]] = field(default_factory=list)
    target_fixed: bool = True
    regression_count: int = 0
    passed: bool = True

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["regression"] = self.regression_count
        return payload

    def summary_line(self) -> str:
        return f"Regression: {self.regression_count}"


def _ids(report: EvaluationReport, *, passed: bool) -> set[str]:
    return {result.scenario_id for result in report.results if result.passed is passed}


def _critical(report: EvaluationReport) -> list[FailureRecord]:
    return [
        failure
        for result in report.results
        for failure in result.failures
        if failure.severity == "critical"
    ]


def compare_reports(before: EvaluationReport, after: EvaluationReport) -> RegressionReport:
    before_pass = _ids(before, passed=True)
    before_fail = _ids(before, passed=False)
    after_pass = _ids(after, passed=True)
    after_fail = _ids(after, passed=False)

    still_passing = sorted(before_pass & after_pass)
    still_failing = sorted(before_fail & after_fail)
    newly_passing = sorted(after_pass - before_pass)
    regressions = sorted(before_pass & after_fail)
    target_fixed = before_fail <= after_pass
    critical = [failure.as_dict() for failure in _critical(after)]
    passed = not regressions and not critical

    return RegressionReport(
        still_passing=still_passing,
        still_failing=still_failing,
        newly_passing=newly_passing,
        regressions=regressions,
        critical_safety_regressions=critical,
        target_fixed=target_fixed,
        regression_count=len(regressions),
        passed=passed,
    )
