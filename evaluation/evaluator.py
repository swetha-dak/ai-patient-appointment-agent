"""Deterministic evaluator. Inspects tools, arguments, results, and SQLite — not an LLM judge."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

from backend.agent import agent as agent_module
from backend.agent import tool_runtime
from backend.agent.sessions import clear_all_sessions, run_session_turn
from backend.agent.tool_runtime import MUTATING_TOOLS, execute_tool_call
from backend.database import get_connection
from backend.database.database import PROJECT_ROOT
from backend.database.seed import seed_database
from evaluation.failures import FailureRecord, detect_failures
from evaluation.scenarios import ExpectedRow, ExpectedToolCall, Scenario, all_scenarios, get_scenario
from evaluation.scoring import WEIGHTS, overall_score, score_scenario

ALLOWED_TABLES = {"patients", "doctors", "availability", "appointments"}
PATIENT_ID_RE = re.compile(r"\bPAT-\d+\b", re.I)
YES_RE = re.compile(r"^\s*(yes|yeah|yep|y|ok|okay)\b", re.I)
SUCCESS_CLAIM_RE = re.compile(r"\bbooked appointment\b|\brescheduled appointment\b", re.I)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ScenarioResult:
    scenario_id: str
    title: str
    passed: bool
    checks: list[CheckResult]
    responses: list[str]
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    failures: list[FailureRecord] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "passed": self.passed,
            "score": self.scores.get("overall", 0.0),
            "scores": self.scores,
            "failures": [failure.as_dict() for failure in self.failures],
            "checks": [asdict(check) for check in self.checks],
            "responses": self.responses,
            "tool_trace": self.tool_trace,
        }


@dataclass
class EvaluationReport:
    results: list[ScenarioResult]

    @property
    def passed_count(self) -> int:
        return sum(1 for result in self.results if result.passed)

    def as_dict(self) -> dict[str, Any]:
        scores = [result.scores for result in self.results]
        return {
            "passed": self.passed_count,
            "total": len(self.results),
            "overall_score": overall_score(scores) if scores else 0.0,
            "weights": WEIGHTS,
            "failures": [failure.as_dict() for result in self.results for failure in result.failures],
            "results": [result.as_dict() for result in self.results],
        }

    def summary_lines(self) -> list[str]:
        lines = [
            (
                f"Scenario {index:02d} ({result.scenario_id}): "
                f"{'PASS' if result.passed else 'FAIL'} "
                f"{result.scores.get('overall', 0.0):g}% — {result.title}"
            )
            for index, result in enumerate(self.results, start=1)
        ]
        payload = self.as_dict()
        lines.append(f"Passed {self.passed_count}/{len(self.results)}")
        lines.append(f"Overall score: {payload['overall_score']}%")
        failure_count = len(payload["failures"])
        lines.append(f"Structured failures: {failure_count}")
        return lines


@contextmanager
def _evaluation_database() -> Iterator[None]:
    previous = os.environ.get("DATABASE_PATH")
    os.environ["DATABASE_PATH"] = str(PROJECT_ROOT / "data" / "eval.db")
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = previous


@contextmanager
def _disable_ollama() -> Iterator[None]:
    previous = os.environ.get("OLLAMA_BASE_URL")
    os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OLLAMA_BASE_URL", None)
        else:
            os.environ["OLLAMA_BASE_URL"] = previous


def _args_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if actual.get(key) != value:
            return False
    return True


def _find_tool(trace: list[dict[str, Any]], expected: ExpectedToolCall) -> dict[str, Any] | None:
    for item in trace:
        if item["name"] != expected.name:
            continue
        if _args_match(expected.args_contains, item["args"]):
            return item
    return None


def _check_database(expected: ExpectedRow) -> CheckResult:
    if expected.table not in ALLOWED_TABLES:
        return CheckResult("database", False, f"Unknown table {expected.table}")
    clauses = []
    params: list[Any] = []
    for key, value in expected.where.items():
        if not re.fullmatch(r"[a-z_]+", key):
            return CheckResult("database", False, f"Invalid column {key}")
        clauses.append(f"{key} = ?")
        params.append(value)
    sql = f"SELECT 1 FROM {expected.table} WHERE {' AND '.join(clauses)} LIMIT 1"
    connection = get_connection()
    try:
        found = connection.execute(sql, params).fetchone() is not None
    finally:
        connection.close()
    ok = found if expected.exists else not found
    detail = f"{expected.table} {expected.where} exists={found} (wanted exists={expected.exists})"
    return CheckResult(f"db:{expected.table}", ok, detail)


class _ToolProbe:
    def __init__(self, inject_fault: dict[str, Any] | None) -> None:
        self.inject_fault = inject_fault
        self.turn_index = 0
        self.trace: list[dict[str, Any]] = []
        self._original = execute_tool_call

    def __call__(
        self,
        name: str,
        args: dict[str, Any] | None,
        *,
        user_confirmed: bool = False,
    ) -> dict[str, Any]:
        payload = dict(args or {})
        if name in MUTATING_TOOLS:
            payload["confirmed"] = user_confirmed is True
        if self.inject_fault and name == self.inject_fault.get("tool"):
            result: dict[str, Any] = {
                "ok": False,
                "error": {
                    "code": self.inject_fault.get("error_code", "DATABASE_ERROR"),
                    "message": self.inject_fault.get("message", "Injected evaluation fault"),
                },
                "data": None,
            }
        else:
            result = self._original(name, args, user_confirmed=user_confirmed)
        self.trace.append(
            {
                "turn_index": self.turn_index,
                "name": name,
                "args": payload,
                "ok": bool(result.get("ok")),
                "result": result,
            }
        )
        return result

    def install(self) -> None:
        tool_runtime.execute_tool_call = self  # type: ignore[assignment]
        agent_module.execute_tool_call = self  # type: ignore[assignment]


def _restore_execute() -> None:
    tool_runtime.execute_tool_call = execute_tool_call
    agent_module.execute_tool_call = execute_tool_call


def _session_id_for_message(base: str, message: str, previous: str | None) -> str:
    match = PATIENT_ID_RE.search(message)
    if match:
        return f"{base}:{match.group(0).upper()}"
    return previous or base


def evaluate_scenario(scenario: Scenario) -> ScenarioResult:
    checks: list[CheckResult] = []
    responses: list[str] = []
    inject_fault = scenario.initial_state.get("inject_fault")
    probe = _ToolProbe(inject_fault)
    trace: list[dict[str, Any]] = probe.trace
    current_session: str | None = None
    try:
        probe.install()
        if scenario.initial_state.get("reset_database", True):
            seed_database(reset=True)
        clear_all_sessions()
        base_session = str(scenario.initial_state.get("session_id") or scenario.scenario_id)
        for turn_index, message in enumerate(scenario.conversation):
            current_session = _session_id_for_message(base_session, message, current_session)
            probe.turn_index = turn_index
            state = run_session_turn(current_session, message)
            responses.append(str(state.get("response") or ""))

        for expected in scenario.expected_tool_calls:
            found = _find_tool(trace, expected)
            if found:
                checks.append(
                    CheckResult(
                        f"tool:{expected.name}",
                        True,
                        f"Found {expected.name} with {expected.args_contains or 'any args'}",
                    )
                )
            else:
                checks.append(
                    CheckResult(
                        f"tool:{expected.name}",
                        False,
                        f"Missing {expected.name} containing {expected.args_contains}",
                    )
                )

        for forbidden in scenario.forbidden_tool_names:
            used = [item for item in trace if item["name"] == forbidden]
            checks.append(
                CheckResult(
                    f"forbidden_tool:{forbidden}",
                    not used,
                    f"calls={len(used)}" if used else "not called",
                )
            )

        for item in trace:
            if item["name"] not in MUTATING_TOOLS:
                continue
            if item["args"].get("confirmed") is not True:
                continue
            turn = item["turn_index"]
            user_text = scenario.conversation[turn] if 0 <= turn < len(scenario.conversation) else ""
            allowed = bool(YES_RE.match(user_text))
            checks.append(
                CheckResult(
                    "confirmation_before_mutation",
                    allowed,
                    f"{item['name']} confirmed=True on turn {turn}: {user_text!r}",
                )
            )

        combined = "\n".join(responses)
        booked_ids = [
            str(row.where.get("appointment_id"))
            for row in scenario.expected_database
            if row.table == "appointments"
            and row.exists
            and row.where.get("appointment_id")
            and (
                row.where.get("appointment_id") != "APT-001"
                or scenario.scenario_id == "scenario_08"
            )
        ]
        claimed = bool(SUCCESS_CLAIM_RE.search(combined))
        if claimed:
            connection = get_connection()
            try:
                persisted = connection.execute(
                    "SELECT appointment_id FROM appointments WHERE status = 'booked'"
                ).fetchall()
                persisted_ids = {row["appointment_id"] for row in persisted}
            finally:
                connection.close()
            invented = [
                match.group(0)
                for match in re.finditer(r"\bAPT-\d+\b", combined, re.I)
                if match.group(0).upper() not in persisted_ids
            ]
            checks.append(
                CheckResult(
                    "no_fake_success",
                    not invented,
                    f"response ids not in sqlite: {invented}" if invented else "success claims match sqlite",
                )
            )
        elif booked_ids:
            mentioned = all(appointment_id in combined for appointment_id in booked_ids)
            checks.append(
                CheckResult(
                    "reports_persisted_ids",
                    mentioned,
                    "response mentions expected appointment ids" if mentioned else f"missing {booked_ids} in {combined!r}",
                )
            )

        for row in scenario.expected_database:
            checks.append(_check_database(row))
    finally:
        _restore_execute()

    passed = all(check.passed for check in checks)
    result = ScenarioResult(
        scenario_id=scenario.scenario_id,
        title=scenario.title,
        passed=passed,
        checks=checks,
        responses=responses,
        tool_trace=trace,
    )
    result.scores = score_scenario(result, scenario)
    result.failures = detect_failures(scenario.scenario_id, checks)
    return result


def evaluate_all(scenario_ids: list[str] | None = None) -> EvaluationReport:
    selected = [get_scenario(item) for item in scenario_ids] if scenario_ids else all_scenarios()
    results: list[ScenarioResult] = []
    with _evaluation_database(), _disable_ollama():
        for scenario in selected:
            results.append(evaluate_scenario(scenario))
    return EvaluationReport(results=results)


def main() -> None:
    report = evaluate_all()
    print("\n".join(report.summary_lines()))
    failed = [result for result in report.results if not result.passed]
    for result in failed:
        print(f"\n{result.scenario_id} failures:")
        for failure in result.failures:
            print(
                f"  - [{failure.severity}] {failure.failure_type}: {failure.problem}"
            )


if __name__ == "__main__":
    main()
