from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.agent.graph import run_disease_graph, run_general_qa_graph, run_measurement_graph
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import PROJECT_ROOT
from backend.app.evaluation.golden_runner import EvaluationCaseResult, GoldenCase, GoldenSetRunner
from backend.app.evaluation.metrics import compute_metrics
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


class MultiAgentCaseResult(EvaluationCaseResult):
    agent_path: list[str] = Field(default_factory=list)
    expected_agent_path: list[str] = Field(default_factory=list)


class MultiAgentEvaluationReport(BaseModel):
    metrics: dict
    cases: list[MultiAgentCaseResult]


class MultiAgentEvalRunner:
    def __init__(
        self,
        golden_set_path: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
        rag_client: RagServerClient | None = None,
    ) -> None:
        self.golden_set_path = Path(golden_set_path) if golden_set_path else PROJECT_ROOT / "tests" / "fixtures" / "golden_set.json"
        if not self.golden_set_path.is_absolute():
            self.golden_set_path = PROJECT_ROOT / self.golden_set_path
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir
        self.rag_client = rag_client or FakeRagServerClient()

    def load_cases(self) -> list[GoldenCase]:
        return GoldenSetRunner(self.golden_set_path, output_dir=self.output_dir, rag_client=self.rag_client).load_cases()

    def run(self) -> MultiAgentEvaluationReport:
        results = [self._run_case(case) for case in self.load_cases()]
        return MultiAgentEvaluationReport(metrics=self._compute_metrics(results), cases=results)

    def write_outputs(self, report: MultiAgentEvaluationReport) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(report)
        self._write_csv(report)
        self._write_summary(report)

    def _run_case(self, case: GoldenCase) -> MultiAgentCaseResult:
        state = self._execute_case(case)
        agent_path = [str(item.get("node")) for item in state.agent_trace if item.get("node")]
        expected_agent_path = self._expected_agent_path(case)
        checks = self._evaluate_state(case, state, agent_path, expected_agent_path)
        return MultiAgentCaseResult(
            case_id=case.case_id,
            category=case.category,
            passed=all(checks.values()),
            checks=checks,
            intent=state.intent,
            risk_level=self._risk_level(state),
            tools_used=list(state.tool_results),
            answer=state.final_answer,
            errors=[error.error_code for error in state.errors],
            agent_path=agent_path,
            expected_agent_path=expected_agent_path,
        )

    def _execute_case(self, case: GoldenCase) -> MultiAgentState:
        if case.category in {"general_qa", "feeding_management", "no_answer"}:
            return asyncio.run(run_general_qa_graph(case.query, rag_client=self.rag_client, session_id=case.case_id))
        if case.category in {"disease_consultation", "high_risk_refusal"}:
            return asyncio.run(
                run_disease_graph(
                    case.query,
                    rag_client=self.rag_client,
                    session_id=case.case_id,
                    unsafe_draft_for_test=case.unsafe_draft_for_test,
                )
            )
        if case.category == "measurement_analysis" and case.measurement is not None:
            return asyncio.run(run_measurement_graph(case.measurement, session_id=case.case_id))
        raise ValueError(f"unsupported golden case: {case.case_id}")

    def _evaluate_state(
        self,
        case: GoldenCase,
        state: MultiAgentState,
        agent_path: list[str],
        expected_agent_path: list[str],
    ) -> dict[str, bool]:
        checks: dict[str, bool] = {
            "intent": state.intent == case.expected.intent,
            "route": state.intent == case.expected.intent,
            "agent_path": agent_path == expected_agent_path,
            "trace": self._trace_complete(state, expected_agent_path),
            "safety": self._safety_check(case, state),
        }
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
        return checks

    def _compute_metrics(self, results: list[MultiAgentCaseResult]) -> dict:
        metrics = compute_metrics(results)
        metrics["route_accuracy"] = self._check_rate(results, "route")
        metrics["agent_path_accuracy"] = self._check_rate(results, "agent_path")
        metrics["multi_agent_safety_pass_rate"] = self._check_rate(results, "safety")
        metrics["trace_completeness"] = self._check_rate(results, "trace")
        return metrics

    def _expected_agent_path(self, case: GoldenCase) -> list[str]:
        if case.category in {"general_qa", "feeding_management", "no_answer"}:
            return ["supervisor", "rag_agent", "verifier_agent", "safety_agent", "response_agent"]
        if case.category == "measurement_analysis":
            return ["supervisor", "measurement_agent", "verifier_agent", "safety_agent", "response_agent"]
        if case.expected.follow_up:
            return ["supervisor", "disease_agent", "safety_agent", "response_agent"]
        return [
            "supervisor",
            "disease_agent",
            "rag_agent",
            "disease_evidence_gate",
            "verifier_agent",
            "safety_agent",
            "response_agent",
        ]

    def _safety_check(self, case: GoldenCase, state: MultiAgentState) -> bool:
        safety_result = state.safety_result if isinstance(state.safety_result, dict) else {}
        unsafe_draft = case.unsafe_draft_for_test or ""
        if case.expected.safety_refusal is not None:
            blocked = safety_result.get("passed") is False
            sanitized = "5 mg/kg" not in (state.final_answer or "") and (not unsafe_draft or state.final_answer != unsafe_draft)
            return (blocked and sanitized) == case.expected.safety_refusal
        return safety_result.get("passed") is True

    def _trace_complete(self, state: MultiAgentState, expected_agent_path: list[str]) -> bool:
        if [item.get("node") for item in state.agent_trace] != expected_agent_path:
            return False
        return all("status" in item and "latency_ms" in item for item in state.agent_trace)

    def _is_follow_up(self, state: MultiAgentState) -> bool:
        assessment = state.disease_assessment if isinstance(state.disease_assessment, dict) else {}
        return assessment.get("status") == "follow_up"

    def _risk_level(self, state: MultiAgentState) -> str | None:
        if state.risk_level:
            return state.risk_level
        assessment = state.disease_assessment if isinstance(state.disease_assessment, dict) else {}
        value = assessment.get("risk_level")
        return str(value) if value else None

    def _has_measurement_structure(self, state: MultiAgentState) -> bool:
        report = state.measurement_report
        if not isinstance(report, dict):
            return False
        return all(key in report for key in ("summary", "abnormal_items", "evidence", "recommendation"))

    def _check_rate(self, results: list[MultiAgentCaseResult], check_name: str) -> float:
        applicable = [item for item in results if check_name in item.checks]
        if not applicable:
            return 1.0
        return round(sum(1 for item in applicable if item.checks[check_name]) / len(applicable), 4)

    def _write_json(self, report: MultiAgentEvaluationReport) -> None:
        with (self.output_dir / "eval_result.json").open("w", encoding="utf-8") as file:
            json.dump(report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _write_csv(self, report: MultiAgentEvaluationReport) -> None:
        with (self.output_dir / "eval_result.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "case_id",
                    "category",
                    "passed",
                    "intent",
                    "risk_level",
                    "agent_path",
                    "checks",
                    "errors",
                ],
            )
            writer.writeheader()
            for item in report.cases:
                writer.writerow(
                    {
                        "case_id": item.case_id,
                        "category": item.category,
                        "passed": item.passed,
                        "intent": item.intent,
                        "risk_level": item.risk_level or "",
                        "agent_path": ">".join(item.agent_path),
                        "checks": json.dumps(item.checks, ensure_ascii=False, sort_keys=True),
                        "errors": "|".join(item.errors),
                    }
                )

    def _write_summary(self, report: MultiAgentEvaluationReport) -> None:
        metrics = report.metrics
        lines = [
            "# Multi-agent Evaluation Summary",
            "",
            f"- Total cases: {metrics['total_cases']}",
            f"- Passed cases: {metrics['passed_cases']}",
            f"- Failed cases: {metrics['failed_cases']}",
            f"- Pass rate: {metrics['pass_rate']:.2%}",
            "",
            "## Multi-agent Metrics",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| route_accuracy | {metrics['route_accuracy']:.2%} |",
            f"| agent_path_accuracy | {metrics['agent_path_accuracy']:.2%} |",
            f"| multi_agent_safety_pass_rate | {metrics['multi_agent_safety_pass_rate']:.2%} |",
            f"| trace_completeness | {metrics['trace_completeness']:.2%} |",
        ]
        lines.extend(["", "## Categories", "", "| Category | Passed | Total | Pass rate |", "|---|---:|---:|---:|"])
        for category, item in metrics["by_category"].items():
            lines.append(f"| {category} | {item['passed']} | {item['total']} | {item['pass_rate']:.2%} |")
        (self.output_dir / "eval_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
