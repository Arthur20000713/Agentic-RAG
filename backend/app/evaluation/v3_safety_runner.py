from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.agent.safety_agent import SafetyAgent
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import PROJECT_ROOT


class V3SafetyCase(BaseModel):
    case_id: str
    prompt: str
    unsafe_answer: str
    expected_violations: list[str] = Field(default_factory=list)


class V3SafetyCaseResult(BaseModel):
    case_id: str
    passed: bool
    expected_violations: list[str] = Field(default_factory=list)
    actual_violations: list[str] = Field(default_factory=list)
    hard_blocked: bool = False
    sanitized: bool = False
    final_answer: str | None = None


class V3SafetyEvaluationReport(BaseModel):
    metrics: dict
    cases: list[V3SafetyCaseResult]


class V3SafetyEvalRunner:
    def __init__(
        self,
        fixture_path: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
    ) -> None:
        self.fixture_path = Path(fixture_path) if fixture_path else PROJECT_ROOT / "tests" / "fixtures" / "v3_safety_redteam.json"
        if not self.fixture_path.is_absolute():
            self.fixture_path = PROJECT_ROOT / self.fixture_path
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports" / "v3_safety"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir

    def load_cases(self) -> list[V3SafetyCase]:
        with self.fixture_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, list):
            raise ValueError("v3 safety red-team fixture must be a JSON list")
        return [V3SafetyCase.model_validate(item) for item in payload]

    def run(self) -> V3SafetyEvaluationReport:
        results = [self._run_case(case) for case in self.load_cases()]
        return V3SafetyEvaluationReport(metrics=self._metrics(results), cases=results)

    def write_outputs(self, report: V3SafetyEvaluationReport) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "v3_safety_result.json").write_text(
            json.dumps(report.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            "# V3 Safety Evaluation Summary",
            "",
            f"- Total cases: {report.metrics['total_cases']}",
            f"- Passed cases: {report.metrics['passed_cases']}",
            f"- Safety pass rate: {report.metrics['safety_pass_rate']:.2%}",
            "",
            "| Case | Passed | Violations |",
            "|---|---:|---|",
        ]
        for item in report.cases:
            lines.append(f"| {item.case_id} | {item.passed} | {', '.join(item.actual_violations)} |")
        (self.output_dir / "v3_safety_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _run_case(self, case: V3SafetyCase) -> V3SafetyCaseResult:
        state = MultiAgentState(
            session_id=case.case_id,
            user_query=case.prompt,
            intent="disease_consultation",
            draft_answer=case.unsafe_answer,
        )
        SafetyAgent().check(state)
        safety_result = state.safety_result if isinstance(state.safety_result, dict) else {}
        actual_violations = list(safety_result.get("violations") or [])
        expected_matched = all(item in actual_violations for item in case.expected_violations)
        sanitized = state.final_answer != case.unsafe_answer
        hard_blocked = bool(safety_result.get("hard_blocked"))
        return V3SafetyCaseResult(
            case_id=case.case_id,
            passed=expected_matched and sanitized and hard_blocked,
            expected_violations=case.expected_violations,
            actual_violations=actual_violations,
            hard_blocked=hard_blocked,
            sanitized=sanitized,
            final_answer=state.final_answer,
        )

    def _metrics(self, results: list[V3SafetyCaseResult]) -> dict:
        total = len(results)
        passed = sum(1 for item in results if item.passed)
        failed = total - passed
        return {
            "total_cases": total,
            "passed_cases": passed,
            "failed_cases": failed,
            "safety_pass_rate": round(passed / total, 4) if total else 1.0,
        }
