from __future__ import annotations

import asyncio
import csv
import json
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.app.agent.graph import (
    run_disease_graph,
    run_general_qa_graph,
    run_measurement_graph,
)
from backend.app.agent.safety_precheck import SafetyLevel, SafetyPrecheck
from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.evaluation.agent_runtime_report import build_agent_runtime_report
from backend.app.evaluation.golden_runner import (
    EvaluationCaseResult,
    GoldenCase,
    GoldenSetRunner,
)
from backend.app.evaluation.metrics import compute_metrics
from backend.app.evaluation.real_rag_preflight import RealRagPreflightRunner
from backend.app.evaluation.router_ab_quality_gate import (
    evaluate_router_ab_quality_gate,
)
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient
from backend.app.model.base import BaseModelClient
from backend.app.model.local_client import LocalModelClient
from backend.app.model.primary_llm import resolve_primary_llm_api_key
from backend.app.model.usage import summarize_model_calls


@dataclass(frozen=True)
class AgentRuntimeEvalScenario:
    name: str
    settings: Settings | None = None


class AgentRuntimeCaseResult(EvaluationCaseResult):
    scenario: str
    repeat_index: int = Field(default=1, ge=1)
    route_mode: str | None = None
    selected_model: str | None = None
    agent_path: list[str] = Field(default_factory=list)
    end_to_end_latency_ms: float = Field(default=0, ge=0)
    model_call_count: int = Field(default=0, ge=0)
    model_latency_ms: int = Field(default=0, ge=0)
    known_input_tokens: int = Field(default=0, ge=0)
    known_output_tokens: int = Field(default=0, ge=0)
    known_total_tokens: int = Field(default=0, ge=0)
    tokens_complete: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    known_total_cost_usd: float = Field(default=0, ge=0)
    cost_complete: bool = False
    total_cost_usd: float | None = Field(default=None, ge=0)
    cost_scope: Literal["api_token_only"] = "api_token_only"
    fallback_used: bool = False
    fallback_reasons: list[str] = Field(default_factory=list)
    local_success_call_count: int = Field(default=0, ge=0)
    primary_success_call_count: int = Field(default=0, ge=0)
    primary_reasoning_success_call_count: int = Field(default=0, ge=0)
    local_fallback_call_count: int = Field(default=0, ge=0)
    primary_fallback_call_count: int = Field(default=0, ge=0)
    local_takeover_attempted: bool = False
    local_takeover: bool = False
    local_call: bool = False
    primary_route: bool = False
    primary_call: bool = False
    primary_escalation: bool = False
    actual_rag_call_count: int = Field(default=0, ge=0)
    request_safety_level: SafetyLevel = "S0"
    triage_intent_correct: bool | None = None
    triage_slot_correct: bool | None = None
    triage_risk_correct: bool | None = None


class AgentRuntimeEvaluationReport(BaseModel):
    mode: str = "agent_runtime"
    evidence_kind: Literal["scripted", "real"] = "scripted"
    performance_claim_allowed: bool = False
    claim_eligibility: dict[str, bool] = Field(default_factory=dict)
    benchmark_context: dict[str, Any] = Field(default_factory=dict)
    scenarios: list[str]
    metrics: dict[str, Any]
    cases: list[AgentRuntimeCaseResult]


class AgentRuntimeEvalRunner:
    def __init__(
        self,
        golden_set_path: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
        rag_client: RagServerClient | None = None,
        scenarios: list[AgentRuntimeEvalScenario] | None = None,
        evidence_kind: Literal["scripted", "real"] = "scripted",
        base_settings: Settings | None = None,
        warmup_runs: int = 0,
        measured_repeats: int = 1,
    ) -> None:
        self.golden_set_path = (
            Path(golden_set_path)
            if golden_set_path
            else PROJECT_ROOT / "tests" / "fixtures" / "router_ab_golden.json"
        )
        if not self.golden_set_path.is_absolute():
            self.golden_set_path = PROJECT_ROOT / self.golden_set_path
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir
        self.rag_client = rag_client or FakeRagServerClient()
        self.scenarios = scenarios or self.default_scenarios(base_settings)
        self._triage_clients: dict[str, BaseModelClient] = {}
        if warmup_runs < 0 or measured_repeats < 1:
            raise ValueError("warmup_runs must be non-negative and measured_repeats must be positive")
        self.warmup_runs = warmup_runs
        self.measured_repeats = measured_repeats
        self.rag_preflight_status = "not_run"
        if evidence_kind == "real":
            self._validate_real_evidence()
        self.evidence_kind = evidence_kind

    @staticmethod
    def default_scenarios(base_settings: Settings | None = None) -> list[AgentRuntimeEvalScenario]:
        base = base_settings or Settings()
        return [
            AgentRuntimeEvalScenario("router_off", _scenario_settings(base, enabled=False)),
            AgentRuntimeEvalScenario(
                "router_shadow",
                _scenario_settings(base, enabled=True, shadow_mode=True),
            ),
            AgentRuntimeEvalScenario(
                "router_on",
                _scenario_settings(base, enabled=True, shadow_mode=False),
            ),
        ]

    def load_cases(self) -> list[GoldenCase]:
        return GoldenSetRunner(self.golden_set_path, output_dir=self.output_dir, rag_client=self.rag_client).load_cases()

    def _validate_real_evidence(self) -> None:
        if not isinstance(self.rag_client, RagServerMcpClient):
            raise ValueError("real evidence requires a real MCP RAG client")
        router_on = next((item.settings for item in self.scenarios if item.name == "router_on"), None)
        if (
            router_on is None
            or not router_on.local_model.enabled
            or router_on.local_model.provider == "mock"
            or not router_on.primary_llm.enabled
            or router_on.primary_llm.provider == "mock"
        ):
            raise ValueError("real evidence requires non-mock local and primary model settings")
        if self.warmup_runs < 1 or self.measured_repeats < 3:
            raise ValueError("real evidence requires warmup_runs >= 1 and measured_repeats >= 3")
        if not resolve_primary_llm_api_key(router_on):
            raise ValueError("real evidence requires configured primary model credentials")

    def run(self) -> AgentRuntimeEvaluationReport:
        if self.evidence_kind == "real":
            self._run_real_rag_preflight()
        cases = self.load_cases()
        results: list[AgentRuntimeCaseResult] = []
        if cases:
            for scenario in self.scenarios:
                for _ in range(self.warmup_runs):
                    self._run_case(cases[0], scenario)
        for repeat_index in range(1, self.measured_repeats + 1):
            offset = (repeat_index - 1) % len(self.scenarios)
            ordered_scenarios = self.scenarios[offset:] + self.scenarios[:offset]
            for scenario in ordered_scenarios:
                results.extend(self._run_case(case, scenario, repeat_index) for case in cases)
        metrics = self._compute_metrics(results)
        metrics["fallback_contract"] = self._run_fallback_contract(cases)
        claim_eligibility = self._claim_eligibility(metrics)
        report = AgentRuntimeEvaluationReport(
            evidence_kind=self.evidence_kind,
            performance_claim_allowed=all(claim_eligibility.values()),
            claim_eligibility=claim_eligibility,
            benchmark_context=self._benchmark_context(),
            scenarios=[scenario.name for scenario in self.scenarios],
            metrics=metrics,
            cases=results,
        )
        report.metrics["quality_gate"] = evaluate_router_ab_quality_gate(report).model_dump()
        return report

    def _run_real_rag_preflight(self) -> None:
        settings = next(item.settings for item in self.scenarios if item.name == "router_on")
        preflight = asyncio.run(
            RealRagPreflightRunner(
                settings or Settings(),
                output_dir=self.output_dir,
                client=self.rag_client,
            ).run()
        )
        self.rag_preflight_status = preflight.status
        if preflight.status != "passed":
            detail = preflight.error_code or preflight.error_message or "unknown error"
            raise ValueError(f"real RAG preflight failed: {detail}")

    def write_outputs(self, report: AgentRuntimeEvaluationReport) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(report)
        self._write_csv(report)
        self._write_summary(report)
        self._write_agent_runtime_report(report)

    def _run_case(
        self,
        case: GoldenCase,
        scenario: AgentRuntimeEvalScenario,
        repeat_index: int = 1,
    ) -> AgentRuntimeCaseResult:
        started = time.perf_counter()
        state = self._execute_case(case, scenario)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        checks = self._evaluate_state(case, state)
        records = getattr(state, "model_call_records", [])
        usage = summarize_model_calls(records)
        route_mode = self._route_decision_value(state, "route_mode") or self._default_route_value(scenario, "route_mode")
        selected_model = self._route_decision_value(state, "selected_model") or self._default_route_value(
            scenario, "selected_model"
        )
        triage = getattr(state, "livestock_triage", None)
        local_success_count = self._model_call_count(records, "local_small", {"success"})
        primary_success_count = self._model_call_count(records, "primary", {"success"})
        primary_reasoning_success_count = sum(
            record.selected_model == "primary"
            and record.status == "success"
            and record.task_type in {"planning", "reasoning", "final_answer"}
            for record in records
        )
        local_fallback_count = self._model_call_count(records, "local_small", {"fallback", "error"})
        primary_fallback_count = self._model_call_count(records, "primary", {"fallback", "error"})
        triage_fallback = getattr(triage, "status", None) == "fallback"
        fallback_used = triage_fallback or local_fallback_count > 0 or primary_fallback_count > 0
        local_call = any(record.selected_model == "local_small" for record in records) or getattr(
            triage, "status", None
        ) in {"accepted", "fallback"}
        primary_call = any(record.selected_model == "primary" for record in records)
        local_takeover_attempted = route_mode == "takeover" and selected_model == "local_small"
        local_takeover_accepted = (
            local_takeover_attempted
            and not triage_fallback
            and local_success_count > 0
        )
        triage_quality = self._triage_quality(case, state)
        request_safety_level = SafetyPrecheck().classify(state.user_query).level
        return AgentRuntimeCaseResult(
            case_id=case.case_id,
            category=case.category,
            scenario=scenario.name,
            repeat_index=repeat_index,
            passed=all(checks.values()),
            checks=checks,
            intent=state.intent,
            risk_level=self._risk_level(state),
            tools_used=list(state.tool_results),
            answer=state.final_answer,
            errors=[error.error_code for error in state.errors],
            route_mode=route_mode,
            selected_model=selected_model,
            agent_path=[str(item.get("node")) for item in getattr(state, "agent_trace", []) if item.get("node")],
            end_to_end_latency_ms=elapsed_ms,
            model_call_count=usage["call_count"],
            model_latency_ms=usage["total_latency_ms"],
            known_input_tokens=usage["known_input_tokens"],
            known_output_tokens=usage["known_output_tokens"],
            known_total_tokens=usage["known_total_tokens"],
            tokens_complete=usage["tokens_complete"],
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            known_total_cost_usd=usage["known_total_cost_usd"],
            cost_complete=usage["cost_complete"],
            total_cost_usd=usage["total_cost_usd"],
            fallback_used=fallback_used,
            fallback_reasons=self._fallback_reasons(state, records),
            local_success_call_count=local_success_count,
            primary_success_call_count=primary_success_count,
            primary_reasoning_success_call_count=primary_reasoning_success_count,
            local_fallback_call_count=local_fallback_count,
            primary_fallback_call_count=primary_fallback_count,
            local_takeover_attempted=local_takeover_attempted,
            local_takeover=local_takeover_accepted,
            local_call=local_call,
            primary_route=route_mode == "primary" and selected_model == "primary",
            primary_call=primary_call,
            primary_escalation=(triage_fallback or local_fallback_count > 0) and primary_call,
            actual_rag_call_count=self._actual_rag_call_count(state),
            request_safety_level=request_safety_level,
            **triage_quality,
        )

    def _execute_case(self, case: GoldenCase, scenario: AgentRuntimeEvalScenario):
        settings = scenario.settings or Settings()
        triage_client = self._triage_client(scenario) if settings.model_router.enabled else None
        return self._execute_graph_case(case, settings, triage_client)

    def _execute_graph_case(
        self,
        case: GoldenCase,
        settings: Settings,
        triage_client: BaseModelClient | None = None,
        rag_client: RagServerClient | None = None,
    ):
        active_rag_client = rag_client or self.rag_client
        if case.category in {"general_qa", "feeding_management", "no_answer"}:
            return asyncio.run(
                run_general_qa_graph(
                    case.query,
                    rag_client=active_rag_client,
                    session_id=case.case_id,
                    settings=settings,
                    livestock_triage_client=triage_client,
                )
            )
        if case.category in {"disease_consultation", "high_risk_refusal"}:
            return asyncio.run(
                run_disease_graph(
                    case.query,
                    rag_client=active_rag_client,
                    session_id=case.case_id,
                    unsafe_draft_for_test=case.unsafe_draft_for_test,
                    settings=settings,
                    livestock_triage_client=triage_client,
                )
            )
        if case.category == "measurement_analysis" and case.measurement is not None:
            return asyncio.run(run_measurement_graph(case.measurement, session_id=case.case_id, settings=settings))
        raise ValueError(f"unsupported golden case: {case.case_id}")

    def _triage_client(self, scenario: AgentRuntimeEvalScenario) -> BaseModelClient:
        if scenario.name not in self._triage_clients:
            self._triage_clients[scenario.name] = LocalModelClient(scenario.settings or Settings())
        return self._triage_clients[scenario.name]

    def _run_fallback_contract(self, cases: list[GoldenCase]) -> dict[str, Any]:
        scenario = next((item for item in self.scenarios if item.name == "router_on"), None)
        case = next(
            (
                item
                for item in cases
                if item.category in {"general_qa", "feeding_management", "no_answer", "disease_consultation"}
                and item.expected.rag_call is not False
            ),
            None,
        )
        if scenario is None or case is None:
            return {"executed": False, "passed": False, "evidence_kind": "scripted"}
        settings = scenario.settings or Settings()
        scripted_settings = settings.model_copy(
            update={
                "primary_llm": settings.primary_llm.model_copy(update={"enabled": False}),
                "disease_llm": settings.disease_llm.model_copy(update={"enabled": False}),
            }
        )
        state = self._execute_graph_case(
            case,
            scripted_settings,
            _InjectedFailureModelClient(),
            FakeRagServerClient(),
        )
        triage = getattr(state, "livestock_triage", None)
        return {
            "executed": True,
            "passed": getattr(triage, "status", None) == "fallback" and all(self._evaluate_state(case, state).values()),
            "evidence_kind": "scripted",
            "case_id": case.case_id,
        }

    def _evaluate_state(self, case: GoldenCase, state: Any) -> dict[str, bool]:
        checks: dict[str, bool] = {"intent": state.intent == case.expected.intent}
        if case.expected.rag_call is not None:
            checks["rag_call"] = (self._actual_rag_call_count(state) > 0) == case.expected.rag_call
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

    def _compute_metrics(self, results: list[AgentRuntimeCaseResult]) -> dict[str, Any]:
        metrics = compute_metrics(results)
        metrics["by_scenario"] = {}
        for scenario in [item.name for item in self.scenarios]:
            scenario_results = [item for item in results if item.scenario == scenario]
            metrics["by_scenario"][scenario] = self._scenario_metrics(scenario_results)
        return metrics

    def _benchmark_context(self) -> dict[str, Any]:
        router_on = next((item.settings for item in self.scenarios if item.name == "router_on"), None)
        return {
            "warmup_runs": self.warmup_runs,
            "measured_repeats": self.measured_repeats,
            "rag_preflight_status": self.rag_preflight_status,
            "execution_order": "rotating_scenario_order",
            "warmup_scope": "full_graph_representative_case",
            "platform": platform.system(),
            "platform_release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "local_model": _model_context(router_on.local_model if router_on else None),
            "primary_model": _model_context(router_on.primary_llm if router_on else None),
            "rag": {
                "query_mode": router_on.rag_server.query_mode if router_on else None,
                "collection": router_on.rag_server.collection if router_on else None,
            },
            "pricing": router_on.model_pricing.model_dump(mode="json") if router_on else {},
            "router_scenarios": {
                item.name: _router_context(item.settings.model_router if item.settings else None)
                for item in self.scenarios
            },
        }

    def _claim_eligibility(self, metrics: dict[str, Any]) -> dict[str, bool]:
        scenarios = metrics.get("by_scenario", {})
        required_scenarios = ("router_off", "router_shadow", "router_on")
        runtime_verified = (
            self.evidence_kind == "real"
            and self.rag_preflight_status == "passed"
            and self.warmup_runs >= 1
            and self.measured_repeats >= 3
            and metrics.get("failed_cases") == 0
            and all(
                scenarios.get(name, {}).get("primary_reasoning_success_call_count", 0) > 0
                for name in required_scenarios
            )
            and all(
                scenarios.get(name, {}).get("actual_rag_call_count", 0) > 0
                for name in required_scenarios
            )
            and scenarios.get("router_shadow", {}).get("local_success_call_count", 0) > 0
            and scenarios.get("router_on", {}).get("local_takeover_accepted_count", 0) > 0
        )
        tokens_complete = runtime_verified and all(
            scenarios.get(name, {}).get("tokens_complete") is True
            for name in required_scenarios
        )
        cost_complete = tokens_complete and all(
            scenarios.get(name, {}).get("cost_complete") is True
            for name in required_scenarios
        )
        return {
            "task_success": runtime_verified,
            "latency": runtime_verified,
            "tokens": tokens_complete,
            "cost": cost_complete,
        }

    def _scenario_metrics(self, items: list[AgentRuntimeCaseResult]) -> dict[str, Any]:
        task_metrics = compute_metrics(items)
        total = len(items)
        passed = sum(item.passed for item in items)
        fallback_items = [item for item in items if item.fallback_used]
        tokens_complete = all(item.tokens_complete for item in items)
        cost_complete = all(item.cost_complete for item in items)
        known_input = sum(item.known_input_tokens for item in items)
        known_output = sum(item.known_output_tokens for item in items)
        known_total = sum(item.known_total_tokens for item in items)
        known_cost = sum(item.known_total_cost_usd for item in items)
        high_risk_items = [item for item in items if item.request_safety_level in {"S3", "S4"}]
        s4_items = [item for item in items if item.request_safety_level == "S4"]
        high_risk_takeovers = sum(item.local_takeover for item in high_risk_items)
        high_risk_local_calls = sum(item.local_call for item in high_risk_items)
        task_success_rate = _rate(passed, total)
        return {
            "total": total,
            "passed": passed,
            "pass_rate": task_success_rate,
            "task_success_rate": task_success_rate,
            "intent_accuracy": _optional_accuracy(item.triage_intent_correct for item in items),
            "intent_case_count": _optional_count(item.triage_intent_correct for item in items),
            "slot_accuracy": _optional_accuracy(item.triage_slot_correct for item in items),
            "slot_case_count": _optional_count(item.triage_slot_correct for item in items),
            "risk_accuracy": _optional_accuracy(item.triage_risk_correct for item in items),
            "risk_case_count": _optional_count(item.triage_risk_correct for item in items),
            "safety_pass_rate": _check_accuracy(items, "safety"),
            "safety_case_count": sum("safety" in item.checks for item in items),
            "rag_call_accuracy": task_metrics["rag_call_accuracy"],
            "citation_coverage": task_metrics["citation_coverage"],
            "no_answer_accuracy": task_metrics["no_answer_accuracy"],
            "end_to_end_latency_ms": _latency_summary([item.end_to_end_latency_ms for item in items]),
            "model_latency_ms": _latency_summary([float(item.model_latency_ms) for item in items]),
            "model_call_count": sum(item.model_call_count for item in items),
            "known_input_tokens": known_input,
            "known_output_tokens": known_output,
            "known_total_tokens": known_total,
            "tokens_complete": tokens_complete,
            "input_tokens": known_input if tokens_complete else None,
            "output_tokens": known_output if tokens_complete else None,
            "total_tokens": known_total if tokens_complete else None,
            "known_total_cost_usd": known_cost,
            "cost_complete": cost_complete,
            "total_cost_usd": known_cost if cost_complete else None,
            "average_cost_usd": known_cost / total if cost_complete and total else (0.0 if not total else None),
            "cost_scope": "api_token_only",
            "fallback_rate": _rate(len(fallback_items), total),
            "fallback_success_rate": _rate(sum(item.passed for item in fallback_items), len(fallback_items)),
            "fallback_case_count": len(fallback_items),
            "local_success_call_count": sum(item.local_success_call_count for item in items),
            "primary_success_call_count": sum(item.primary_success_call_count for item in items),
            "primary_reasoning_success_call_count": sum(
                item.primary_reasoning_success_call_count for item in items
            ),
            "local_fallback_call_count": sum(item.local_fallback_call_count for item in items),
            "primary_fallback_call_count": sum(item.primary_fallback_call_count for item in items),
            "local_takeover_attempt_count": sum(item.local_takeover_attempted for item in items),
            "local_takeover_accepted_count": sum(item.local_takeover for item in items),
            "local_takeover_attempt_rate": _rate(sum(item.local_takeover_attempted for item in items), total),
            "local_takeover_rate": _rate(sum(item.local_takeover for item in items), total),
            "local_call_rate": _rate(sum(item.local_call for item in items), total),
            "primary_route_rate": _rate(sum(item.primary_route for item in items), total),
            "primary_call_rate": _rate(sum(item.primary_call for item in items), total),
            "primary_escalation_rate": _rate(sum(item.primary_escalation for item in items), total),
            "high_risk_case_count": len(high_risk_items),
            "s3_case_count": sum(item.request_safety_level == "S3" for item in items),
            "s4_case_count": sum(item.request_safety_level == "S4" for item in items),
            "high_risk_local_takeover_count": high_risk_takeovers,
            "high_risk_local_call_count": high_risk_local_calls,
            "actual_rag_call_count": sum(item.actual_rag_call_count for item in items),
            "s4_actual_rag_call_count": sum(item.actual_rag_call_count for item in s4_items),
        }

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
        triage = getattr(state, "livestock_triage", None)
        decision = getattr(triage, "route_decision", None)
        value = getattr(decision, key, None)
        if value:
            return str(value)
        for tool_name in ("model_router_shadow", "measurement_json_renderer"):
            result = state.tool_results.get(tool_name)
            if not isinstance(result, dict):
                continue
            decision = result.get("route_decision")
            if isinstance(decision, dict) and decision.get(key):
                return str(decision[key])
        return None

    def _default_route_value(self, scenario: AgentRuntimeEvalScenario, key: str) -> str:
        settings = scenario.settings or Settings()
        if key == "selected_model":
            return "primary"
        if not settings.model_router.enabled:
            return "disabled"
        return "shadow" if settings.model_router.shadow_mode else "primary"

    def _actual_rag_call_count(self, state: Any) -> int:
        retrieval = getattr(state, "agentic_retrieval", None)
        count = getattr(retrieval, "rag_call_count", 0)
        return count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0

    def _model_call_count(self, records: list[Any], model: str, statuses: set[str]) -> int:
        return sum(record.selected_model == model and record.status in statuses for record in records)

    def _fallback_reasons(self, state: Any, records: list[Any]) -> list[str]:
        triage = getattr(state, "livestock_triage", None)
        reasons = [getattr(triage, "fallback_reason", None)]
        reasons.extend(
            record.fallback_reason or f"{record.selected_model}_{record.status}"
            for record in records
            if record.status in {"fallback", "error"}
        )
        return list(dict.fromkeys(reason for reason in reasons if reason))

    def _triage_quality(self, case: GoldenCase, state: Any) -> dict[str, bool | None]:
        outcome = getattr(state, "livestock_triage", None)
        if outcome is None or getattr(outcome, "status", None) == "not_run":
            return {
                "triage_intent_correct": None,
                "triage_slot_correct": None,
                "triage_risk_correct": None,
            }
        triage = getattr(outcome, "triage", None)
        intent_correct = triage is not None and triage.intent_candidate == case.expected.intent
        slot_correct: bool | None = None
        if case.expected.triage_slots is not None:
            actual_slots = {slot.name: slot.value for slot in triage.slots} if triage is not None else {}
            slot_correct = actual_slots == case.expected.triage_slots
        risk_correct: bool | None = None
        if case.expected.triage_risk_level is not None:
            risk_correct = triage is not None and triage.risk_candidate == case.expected.triage_risk_level
        return {
            "triage_intent_correct": intent_correct,
            "triage_slot_correct": slot_correct,
            "triage_risk_correct": risk_correct,
        }

    def _write_json(self, report: AgentRuntimeEvaluationReport) -> None:
        with (self.output_dir / "eval_result.json").open("w", encoding="utf-8") as file:
            json.dump(report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _write_csv(self, report: AgentRuntimeEvaluationReport) -> None:
        with (self.output_dir / "eval_result.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "scenario",
                    "repeat_index",
                    "case_id",
                    "category",
                    "passed",
                    "intent",
                    "risk_level",
                    "route_mode",
                    "selected_model",
                    "end_to_end_latency_ms",
                    "model_call_count",
                    "model_latency_ms",
                    "total_tokens",
                    "total_cost_usd",
                    "fallback_used",
                    "fallback_reasons",
                    "local_takeover_attempted",
                    "local_takeover",
                    "local_call",
                    "primary_route",
                    "primary_call",
                    "primary_escalation",
                    "actual_rag_call_count",
                    "checks",
                    "errors",
                ],
            )
            writer.writeheader()
            for item in report.cases:
                writer.writerow(
                    {
                        "scenario": item.scenario,
                        "repeat_index": item.repeat_index,
                        "case_id": item.case_id,
                        "category": item.category,
                        "passed": item.passed,
                        "intent": item.intent,
                        "risk_level": item.risk_level or "",
                        "route_mode": item.route_mode or "",
                        "selected_model": item.selected_model or "",
                        "end_to_end_latency_ms": item.end_to_end_latency_ms,
                        "model_call_count": item.model_call_count,
                        "model_latency_ms": item.model_latency_ms,
                        "total_tokens": item.total_tokens if item.tokens_complete else "",
                        "total_cost_usd": item.total_cost_usd if item.cost_complete else "",
                        "fallback_used": item.fallback_used,
                        "fallback_reasons": "|".join(item.fallback_reasons),
                        "local_takeover_attempted": item.local_takeover_attempted,
                        "local_takeover": item.local_takeover,
                        "local_call": item.local_call,
                        "primary_route": item.primary_route,
                        "primary_call": item.primary_call,
                        "primary_escalation": item.primary_escalation,
                        "actual_rag_call_count": item.actual_rag_call_count,
                        "checks": json.dumps(item.checks, ensure_ascii=False, sort_keys=True),
                        "errors": "|".join(item.errors),
                    }
                )

    def _write_summary(self, report: AgentRuntimeEvaluationReport) -> None:
        metrics = report.metrics
        lines = [
            "# Agent Runtime Evaluation Summary",
            "",
            f"- Total cases: {metrics['total_cases']}",
            f"- Passed cases: {metrics['passed_cases']}",
            f"- Failed cases: {metrics['failed_cases']}",
            f"- Pass rate: {metrics['pass_rate']:.2%}",
            f"- Evidence kind: {report.evidence_kind}",
            f"- Performance claim allowed: {str(report.performance_claim_allowed).lower()}",
            f"- Warm-up runs: {report.benchmark_context['warmup_runs']}",
            f"- Measured repeats: {report.benchmark_context['measured_repeats']}",
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

    def _write_agent_runtime_report(self, report: AgentRuntimeEvaluationReport) -> None:
        agent_runtime_report = build_agent_runtime_report(report)
        with (self.output_dir / "agent_runtime_report.json").open("w", encoding="utf-8") as file:
            json.dump(agent_runtime_report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")
        (self.output_dir / "agent_runtime_report.md").write_text(agent_runtime_report.to_markdown(), encoding="utf-8")


def _check_accuracy(items: list[AgentRuntimeCaseResult], check_name: str) -> float | None:
    applicable = [item for item in items if check_name in item.checks]
    if not applicable:
        return None
    return _rate(sum(item.checks[check_name] for item in applicable), len(applicable))


def _optional_accuracy(values: Any) -> float | None:
    applicable = [value for value in values if value is not None]
    if not applicable:
        return None
    return _rate(sum(applicable), len(applicable))


def _optional_count(values: Any) -> int:
    return sum(value is not None for value in values)


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {"p50": round(_percentile(values, 0.50), 3), "p95": round(_percentile(values, 0.95), 3)}


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _rate(numerator: int, denominator: int) -> float:
    if not denominator:
        return 1.0
    return round(numerator / denominator, 4)


def _scenario_settings(base: Settings, *, enabled: bool, shadow_mode: bool = True) -> Settings:
    return base.model_copy(
        update={
            "model_router": base.model_router.model_copy(
                update={
                    "enabled": enabled,
                    "shadow_mode": shadow_mode,
                    "allow_low_risk_takeover": enabled,
                    "takeover_task_types": ["livestock_triage", "measurement_analysis"],
                }
            ),
            "local_model": base.local_model.model_copy(update={"enabled": enabled}),
        }
    )


def _model_context(settings: Any) -> dict[str, Any]:
    if settings is None:
        return {"enabled": False, "provider": None, "model": None}
    return {
        "enabled": settings.enabled,
        "provider": settings.provider,
        "model": settings.model,
    }


def _router_context(settings: Any) -> dict[str, Any]:
    if settings is None:
        return {}
    return {
        "enabled": settings.enabled,
        "shadow_mode": settings.shadow_mode,
        "allow_low_risk_takeover": settings.allow_low_risk_takeover,
        "takeover_task_types": list(settings.takeover_task_types),
        "blocked_safety_levels": list(settings.blocked_safety_levels),
    }


class _InjectedFailureModelClient(BaseModelClient):
    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise TimeoutError("injected router evaluation failure")
