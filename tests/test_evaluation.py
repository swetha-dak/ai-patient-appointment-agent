from evaluation.evaluator import CheckResult, evaluate_all
from evaluation.failures import detect_failures
from evaluation.scoring import WEIGHTS, score_scenario
from evaluation.scenarios import get_scenario


def test_failure_detection_shapes_unsafe_booking():
    records = detect_failures(
        "scenario_03",
        [CheckResult("confirmation_before_mutation", False, "booked on turn 0")],
    )
    assert records[0].failure_type == "unsafe_booking"
    assert records[0].severity == "critical"
    assert records[0].scenario_id == "scenario_03"


def test_scoring_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 2) == 1.0


def test_evaluate_booking_without_confirmation_scenario():
    report = evaluate_all(["scenario_03"])
    assert len(report.results) == 1
    result = report.results[0]
    assert result.passed is True
    scores = score_scenario(result, get_scenario("scenario_03"))
    assert scores["overall"] == 100.0
    assert result.failures == []
