from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.graph import run_disease_graph, run_general_qa_graph, run_measurement_graph
from backend.app.agent.workflow import run_disease_consultation, run_general_qa, run_measurement_analysis
from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.evaluation.golden_runner import EvaluationCaseResult, GoldenCase, GoldenSetRunner
from backend.app.evaluation.metrics import compute_metrics
from backend.app.evaluation.v3_report import build_v3_report
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


@dataclass(frozen=True)
class V3EvalScenario:
    name: str
    settings: Settings | None = None


class V3CaseResult(EvaluationCaseResult):
    scenario: str
    route_mode: str | None = None
    selected_model: str | None = None
    agent_path: list[str] = Field(default_factory=list)


class V3EvaluationReport(BaseModel):
    mode: str = "v3"
    scenarios: list[str]
    metrics: dict[str, Any]
    cases: list[V3CaseResult]


class V3EvalRunner:
    def __init__(
        self,
        golden_set_path: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
        rag_client: RagServerClient | None = None,
        scenarios: list[V3EvalScenario] | None = None,
    ) -> None:
        self.golden_set_path = Path(golden_set_path) if golden_set_path else PROJECT_ROOT / "tests" / "fixtures" / "golden_set.json"
        if not self.golden_set_path.is_absolute():
            self.golden_set_path = PROJECT_ROOT / self.golden_set_path
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir
        self.rag_client = rag_client or FakeRagServerClient()
        self.scenarios = scenarios or self.default_scenarios()

    @staticmethod
    def default_scenarios() -> list[V3EvalScenario]:
        return [
            V3EvalScenario("v2_baseline"),
            V3EvalScenario("v3_off", Settings(v3={"enabled": False})),
            V3EvalScenario(
                "router_shadow",
                Settings(
                    v3={"enabled": True},
                    model_router={"enabled": True, "shadow_mode": True, "allow_low_risk_takeover": True},
                    local_model={"enabled": True},
                ),
            ),
            V3EvalScenario(
                "router_low_risk",
                Settings(
                    v3={"enabled": True},
                    model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
                    local_model={"enabled": True},
                ),
            ),
        ]

    def load_cases(self) -> list[GoldenCase]:
        return GoldenSetRunner(self.golden_set_path, output_dir=self.output_dir, rag_client=self.rag_client).load_cases()

    def run(self) -> V3EvaluationReport:
        cases = self.load_cases()
        results = [self._run_case(case, scenario) for scenario in self.scenarios for case in cases]
        return V3EvaluationReport(
            scenarios=[scenario.name for scenario in self.scenarios],
            metrics=self._compute_metrics(results),
            cases=results,
        )

    def write_outputs(self, report: V3EvaluationReport) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(report)
        self._write_csv(report)
        self._write_summary(report)
        self._write_v3_report(report)

    def _run_case(self, case: GoldenCase, scenario: V3EvalScenario) -> V3CaseResult:
        state = self._execute_case(case, scenario)
        checks = self._evaluate_state(case, state)
        return V3CaseResult(
            case_id=case.case_id,
            category=case.category,
            scenario=scenario.name,
            passed=all(checks.values()),
            checks=checks,
            intent=state.intent,
            risk_level=self._risk_level(state),
            tools_used=list(state.tool_results),
            answer=state.final_answer,
            errors=[error.error_code for error in state.errors],
            route_mode=self._route_decision_value(state, "route_mode"),
            selected_model=self._route_decision_value(state, "selected_model"),
            agent_path=[str(item.get("node")) for item in getattr(state, "agent_trace", []) if item.get("node")],
        )

    def _execute_case(self, case: GoldenCase, scenario: V3EvalScenario):
        if scenario.name == "v2_baseline":
            return self._execute_v2_case(case)
        return self._execute_v3_case(case, scenario.settings or Settings())

    def _execute_v2_case(self, case: GoldenCase):
        if case.category in {"general_qa", "feeding_management", "no_answer"}:
            return asyncio.run(run_general_qa(case.query, rag_client=self.rag_client, session_id=case.case_id))
        if case.category in {"disease_consultation", "high_risk_refusal"}:
            return asyncio.run(
                run_disease_consultation(
                    case.query,
                    rag_client=self.rag_client,
                    session_id=case.case_id,
                    unsafe_draft_for_test=case.unsafe_draft_for_test,
                )
            )
        if case.category == "measurement_analysis" and case.measurement is not None:
            return asyncio.run(run_measurement_analysis(case.measurement, session_id=case.case_id))
        raise ValueError(f"unsupported golden case: {case.case_id}")

    def _execute_v3_case(self, case: GoldenCase, settings: Settings):
        if case.category in {"general_qa", "feeding_management", "no_answer"}:
            return asyncio.run(
                run_general_qa_graph(
                    case.query,
                    rag_client=self.rag_client,
                    session_id=case.case_id,
                    settings=settings,
                )
            )
        if case.category in {"disease_consultation", "high_risk_refusal"}:
            return asyncio.run(
                run_disease_graph(
                    case.query,
                    rag_client=self.rag_client,
                    session_id=case.case_id,
                    unsafe_draft_for_test=case.unsafe_draft_for_test,
                    settings=settings,
                )
            )
        if case.category == "measurement_analysis" and case.measurement is not None:
            return asyncio.run(run_measurement_graph(case.measurement, session_id=case.case_id, settings=settings))
        raise ValueError(f"unsupported golden case: {case.case_id}")

    def _evaluate_state(self, case: GoldenCase, state: Any) -> dict[str, bool]:
        checks: dict[str, bool] = {"intent": state.intent == case.expected.intent}
        if case.expected.rag_call is not None:
            checks["rag_call"] = ("livestock_rag_search" in state.tool_results) == case.expected.rag_call
        if case.expected.citation is not None:
            checks["citation"] = ("[1]" in (state.final_answer or "")) == case.expected.citation
        if case.expected.no_answer is not None:
            checks["no_answer"] = (not state.retrieved_contexts and "[1]" not in (state.final_answer or "")) == case.expected.no_answer
        if case.expected.follow_up is not None:
            checks["follow_up"] = self._is_follow_up(state) == case.expected.follow_up
        if case.expected.structure is not None:
            checks["structure"] = self._has_measurement_structure(state) == case.expected.structure
        if case.expected.risk_level is not None:
            checks["risk_level"] = self._risk_level(state) == case.expected.risk_level
        checks["safety"] = self._safety_check(case, state)
        return checks

    def _compute_metrics(self, results: list[V3CaseResult]) -> dict[str, Any]:
        metrics = compute_metrics(results)
        metrics["by_scenario"] = {}
        for scenario in [item.name for item in self.scenarios]:
            scenario_results = [item for item in results if item.scenario == scenario]
            passed = sum(1 for item in scenario_results if item.passed)
            total = len(scenario_results)
            metrics["by_scenario"][scenario] = {
                "total": total,
                "passed": passed,
                "pass_rate": round(passed / total, 4) if total else 1.0,
            }
        return metrics

    def _safety_check(self, case: GoldenCase, state: Any) -> bool:
        safety_result = getattr(state, "safety_result", None)
        unsafe_text = case.unsafe_draft_for_test or ""
        if case.expected.safety_refusal is not None:
            blocked = isinstance(safety_result, dict) and safety_result.get("passed") is False
            sanitized = "5 mg/kg" not in (state.final_answer or "") and (not unsafe_text or state.final_answer != unsafe_text)
            if safety_result is None:
                return sanitized == case.expected.safety_refusal
            return (blocked and sanitized) == case.expected.safety_refusal
        if isinstance(safety_result, dict):
            return safety_result.get("passed") is True
        return True

    def _is_follow_up(self, state: Any) -> bool:
        if hasattr(state, "need_follow_up"):
            return bool(state.need_follow_up)
        assessment = state.disease_assessment if isinstance(state.disease_assessment, dict) else {}
        return assessment.get("status") == "follow_up"

    def _risk_level(self, state: Any) -> str | None:
        if state.risk_level:
            return state.risk_level
        assessment = getattr(state, "disease_assessment", None)
        if isinstance(assessment, dict) and assessment.get("risk_level"):
            return str(assessment["risk_level"])
        return None

    def _has_measurement_structure(self, state: Any) -> bool:
        report = getattr(state, "measurement_report", None)
        if not isinstance(report, dict):
            report = state.tool_results.get("body_measurement_analyzer")
        if not isinstance(report, dict):
            return False
        return all(key in report for key in ("summary", "abnormal_items", "evidence", "recommendation"))

    def _route_decision_value(self, state: Any, key: str) -> str | None:
        for tool_name in ("model_router_shadow", "measurement_json_renderer"):
            result = state.tool_results.get(tool_name)
            if not isinstance(result, dict):
                continue
            decision = result.get("route_decision")
            if isinstance(decision, dict) and decision.get(key):
                return str(decision[key])
        return None

    def _write_json(self, report: V3EvaluationReport) -> None:
        with (self.output_dir / "eval_result.json").open("w", encoding="utf-8") as file:
            json.dump(report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _write_csv(self, report: V3EvaluationReport) -> None:
        with (self.output_dir / "eval_result.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "scenario",
                    "case_id",
                    "category",
                    "passed",
                    "intent",
                    "risk_level",
                    "route_mode",
                    "selected_model",
                    "checks",
                    "errors",
                ],
            )
            writer.writeheader()
            for item in report.cases:
                writer.writerow(
                    {
                        "scenario": item.scenario,
                        "case_id": item.case_id,
                        "category": item.category,
                        "passed": item.passed,
                        "intent": item.intent,
                        "risk_level": item.risk_level or "",
                        "route_mode": item.route_mode or "",
                        "selected_model": item.selected_model or "",
                        "checks": json.dumps(item.checks, ensure_ascii=False, sort_keys=True),
                        "errors": "|".join(item.errors),
                    }
                )

    def _write_summary(self, report: V3EvaluationReport) -> None:
        metrics = report.metrics
        lines = [
            "# V3 Evaluation Summary",
            "",
            f"- Total cases: {metrics['total_cases']}",
            f"- Passed cases: {metrics['passed_cases']}",
            f"- Failed cases: {metrics['failed_cases']}",
            f"- Pass rate: {metrics['pass_rate']:.2%}",
            "",
            "## Scenarios",
            "",
            "| Scenario | Passed | Total | Pass rate |",
            "|---|---:|---:|---:|",
        ]
        for scenario, item in metrics["by_scenario"].items():
            lines.append(f"| {scenario} | {item['passed']} | {item['total']} | {item['pass_rate']:.2%} |")
        lines.extend(["", "## Checks", "", "| Metric | Value |", "|---|---:|"])
        for key in (
            "intent_accuracy",
            "rag_call_accuracy",
            "citation_coverage",
            "no_answer_accuracy",
            "safety_pass_rate",
            "follow_up_accuracy",
            "structure_completeness",
        ):
            lines.append(f"| {key} | {metrics[key]:.2%} |")
        (self.output_dir / "eval_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_v3_report(self, report: V3EvaluationReport) -> None:
        v3_report = build_v3_report(report)
        with (self.output_dir / "v3_report.json").open("w", encoding="utf-8") as file:
            json.dump(v3_report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")
        (self.output_dir / "v3_report.md").write_text(v3_report.to_markdown(), encoding="utf-8")
