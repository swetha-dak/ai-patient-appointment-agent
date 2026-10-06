from evaluation.evaluator import EvaluationReport, ScenarioResult
from evaluation.failures import FailureRecord
from evaluation.regression import compare_reports


def _scenario(scenario_id: str, passed: bool, failures: list[FailureRecord] | None = None) -> ScenarioResult:
    return ScenarioResult(scenario_id, scenario_id, passed, [], [], failures=failures or [])


def test_regression_zero_when_target_fixed():
    before = EvaluationReport(
        [_scenario("scenario_01", True), _scenario("scenario_03", False)]
    )
    after = EvaluationReport(
        [_scenario("scenario_01", True), _scenario("scenario_03", True)]
    )
    report = compare_reports(before, after)
    assert report.regression_count == 0
    assert report.target_fixed is True
    assert report.passed is True
    assert report.summary_line() == "Regression: 0"


def test_regression_detects_pass_to_fail_and_critical_safety():
    before = EvaluationReport(
        [_scenario("scenario_01", True), _scenario("scenario_03", False)]
    )
    after = EvaluationReport(
        [
            _scenario(
                "scenario_01",
                False,
                [
                    FailureRecord(
                        "unsafe_booking",
                        "scenario_01",
                        "booked without yes",
                        "critical",
                        "confirmation_before_mutation",
                    )
                ],
            ),
            _scenario("scenario_03", True),
        ]
    )
    report = compare_reports(before, after)
    assert report.regressions == ["scenario_01"]
    assert report.regression_count == 1
    assert report.passed is False
    assert report.critical_safety_regressions
