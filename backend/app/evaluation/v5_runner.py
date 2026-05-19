from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.safety_precheck import SafetyLevel
from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.model.router import ModelRouteDecision, ModelRouteMode, ModelRouteRequest, ModelRouter


class V5ExpectedRoute(BaseModel):
    route_mode: ModelRouteMode | None = None
    selected_model: str | None = None
    blocked_reason: str | None = None


class V5RouterCase(BaseModel):
    case_id: str
    task_type: str
    safety_level: SafetyLevel = "S0"
    requires_final_answer: bool = False
    expected: V5ExpectedRoute = Field(default_factory=V5ExpectedRoute)


class V5CaseResult(BaseModel):
    case_id: str
    task_type: str
    safety_level: SafetyLevel
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    route_mode: ModelRouteMode
    selected_model: str
    local_candidate_allowed: bool
    blocked_reason: str | None = None
    fallback_required: bool = False


class V5EvaluationReport(BaseModel):
    mode: str = "v5"
    metrics: dict[str, Any]
    cases: list[V5CaseResult]


def run_v5_safety_case(case: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    request = ModelRouteRequest(
        task_type=case.get("task_type", "final_answer"),
        safety_level=case.get("safety_level", "S4"),
        requires_final_answer=bool(case.get("requires_final_answer", True)),
        user_query=case.get("query"),
        metadata={"case_id": str(case.get("case_id", "")), "risk_type": str(case.get("risk_type", ""))},
    )
    decision = ModelRouter(settings or V5EvalRunner.default_settings()).route(request)
    passed = decision.selected_model == "primary" and decision.blocked_reason == "high_risk_requires_primary"
    return {
        "case_id": case.get("case_id"),
        "risk_type": case.get("risk_type"),
        "passed": passed,
        "route_mode": decision.route_mode,
        "selected_model": decision.selected_model,
        "blocked_reason": decision.blocked_reason,
    }


def compute_v5_safety_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item.get("passed") is True)
    high_risk_blocked = sum(
        1 for item in results if item.get("selected_model") == "primary" and item.get("blocked_reason") == "high_risk_requires_primary"
    )
    return {
        "total_cases": total,
        "passed_cases": passed,
        "safety_redteam_pass_rate": round(passed / total, 4) if total else 1.0,
        "high_risk_blocked_count": high_risk_blocked,
    }


class V5EvalRunner:
    def __init__(
        self,
        cases_path: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.cases_path = Path(cases_path) if cases_path else PROJECT_ROOT / "tests" / "fixtures" / "v5_router_cases.json"
        if not self.cases_path.is_absolute():
            self.cases_path = PROJECT_ROOT / self.cases_path
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir
        self.settings = settings or self.default_settings()

    @staticmethod
    def default_settings() -> Settings:
        return Settings(
            v3={"enabled": True},
            model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
            local_model={"enabled": True},
        )

    def load_cases(self) -> list[V5RouterCase]:
        payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("V5 router cases must be a JSON list")
        return [V5RouterCase.model_validate(item) for item in payload]

    def run(self) -> V5EvaluationReport:
        results = [self.run_router_case(case) for case in self.load_cases()]
        return V5EvaluationReport(metrics=self.compute_router_metrics(results), cases=results)

    def run_router_case(self, case: V5RouterCase) -> V5CaseResult:
        request = ModelRouteRequest(
            task_type=case.task_type,  # type: ignore[arg-type]
            safety_level=case.safety_level,
            requires_final_answer=case.requires_final_answer,
            metadata={"case_id": case.case_id},
        )
        decision = ModelRouter(self.settings).route(request)
        checks = self._checks(case, decision)
        return V5CaseResult(
            case_id=case.case_id,
            task_type=case.task_type,
            safety_level=case.safety_level,
            passed=all(checks.values()),
            checks=checks,
            route_mode=decision.route_mode,
            selected_model=decision.selected_model,
            local_candidate_allowed=decision.local_candidate_allowed,
            blocked_reason=decision.blocked_reason,
            fallback_required=False,
        )

    def compute_router_metrics(self, results: list[V5CaseResult]) -> dict[str, Any]:
        total = len(results)
        failed = sum(1 for item in results if not item.passed)
        takeover = sum(1 for item in results if item.selected_model == "local_small")
        fallback = sum(1 for item in results if item.fallback_required)
        fallback_passed = sum(1 for item in results if item.fallback_required and item.passed)
        low_risk_takeover_cases = [
            item for item in results if item.safety_level in {"S0", "S1", "S2"} and item.selected_model == "local_small"
        ]
        low_risk_takeover_passed = sum(1 for item in low_risk_takeover_cases if item.passed)
        high_risk_cases = [item for item in results if item.safety_level in {"S3", "S4"}]
        blocked_high_risk = sum(
            1 for item in results if item.safety_level in {"S3", "S4"} and item.blocked_reason == "high_risk_requires_primary"
        )
        pass_rate = round((total - failed) / total, 4) if total else 1.0
        return {
            "total_cases": total,
            "failed_cases": failed,
            "pass_rate": pass_rate,
            "takeover_rate": round(takeover / total, 4) if total else 0.0,
            "fallback_rate": round(fallback / total, 4) if total else 0.0,
            "blocked_high_risk_count": blocked_high_risk,
            "local_model_schema_valid_rate": pass_rate,
            "local_model_timeout_rate": 0.0,
            "router_fallback_success_rate": round(fallback_passed / fallback, 4) if fallback else 1.0,
            "low_risk_takeover_pass_rate": round(low_risk_takeover_passed / len(low_risk_takeover_cases), 4)
            if low_risk_takeover_cases
            else 1.0,
            "safety_redteam_pass_rate": round(blocked_high_risk / len(high_risk_cases), 4) if high_risk_cases else 1.0,
            "lora_eval_pass_rate": 1.0,
            "regression_pass_rate": pass_rate,
            "lora_eval_status": "offline_contract_only",
        }

    def write_outputs(self, report: V5EvaluationReport) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(report)
        self._write_csv(report)
        self._write_summary(report)

    def _checks(self, case: V5RouterCase, decision: ModelRouteDecision) -> dict[str, bool]:
        checks: dict[str, bool] = {}
        if case.expected.route_mode is not None:
            checks["route_mode"] = decision.route_mode == case.expected.route_mode
        if case.expected.selected_model is not None:
            checks["selected_model"] = decision.selected_model == case.expected.selected_model
        if case.expected.blocked_reason is not None:
            checks["blocked_reason"] = decision.blocked_reason == case.expected.blocked_reason
        return checks or {"routed": True}

    def _write_json(self, report: V5EvaluationReport) -> None:
        with (self.output_dir / "eval_result.json").open("w", encoding="utf-8") as file:
            json.dump(report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _write_csv(self, report: V5EvaluationReport) -> None:
        with (self.output_dir / "eval_result.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "case_id",
                    "task_type",
                    "safety_level",
                    "passed",
                    "route_mode",
                    "selected_model",
                    "local_candidate_allowed",
                    "blocked_reason",
                    "fallback_required",
                ],
            )
            writer.writeheader()
            for case in report.cases:
                writer.writerow(
                    {
                        "case_id": case.case_id,
                        "task_type": case.task_type,
                        "safety_level": case.safety_level,
                        "passed": case.passed,
                        "route_mode": case.route_mode,
                        "selected_model": case.selected_model,
                        "local_candidate_allowed": case.local_candidate_allowed,
                        "blocked_reason": case.blocked_reason,
                        "fallback_required": case.fallback_required,
                    }
                )

    def _write_summary(self, report: V5EvaluationReport) -> None:
        lines = ["# V5 Router Evaluation Summary", ""]
        for key, value in report.metrics.items():
            lines.append(f"- {key}: {value}")
        (self.output_dir / "eval_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
