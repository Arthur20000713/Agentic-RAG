from __future__ import annotations

import time
from typing import Any

from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.router import ModelRouteRequest, ModelRouter
from backend.app.schemas.measurement import MeasurementAnalysisResult
from backend.app.schemas.measurement import MeasurementInput
from backend.app.services.measurement_service import MeasurementService


class MeasurementAgent:
    def __init__(self, measurement_service: MeasurementService | None = None, *, settings: Settings | None = None) -> None:
        self.measurement_service = measurement_service or MeasurementService()
        self.settings = settings or Settings()

    def run(self, state: MultiAgentState, measurement: MeasurementInput) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "measurement_agent"

        result = self.measurement_service.analyze(measurement)
        state.measurement_report = result.model_dump()
        state.tool_results["body_measurement_analyzer"] = state.measurement_report
        self._maybe_render_measurement_json(state, result)
        state.draft_answer = result.report
        state.rag_query = None

        state.agent_trace.append(
            {
                "node": "measurement_agent",
                "status": "success",
                "animal_id": result.animal_id,
                "abnormal_count": len(result.abnormal_items),
                "used_demo_history": result.used_demo_history,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    def render_measurement_json(self, result: MeasurementAnalysisResult) -> dict[str, Any]:
        return {
            "animal_id": result.animal_id,
            "summary": result.summary,
            "abnormal_items": list(result.abnormal_items),
            "evidence": list(result.evidence),
            "recommendation": result.recommendation,
            "used_demo_history": result.used_demo_history,
        }

    def _maybe_render_measurement_json(self, state: MultiAgentState, result: MeasurementAnalysisResult) -> None:
        request = ModelRouteRequest(
            task_type="measurement_analysis",
            safety_level="S1",
            requires_final_answer=False,
            user_query=state.normalized_query or state.user_query,
            metadata={"component": "measurement_json_renderer"},
        )
        decision = ModelRouter(self.settings).route(request)
        if decision.selected_model != "local_small":
            return
        state.tool_results["measurement_json_renderer"] = {
            "route_request": request.model_dump(),
            "route_decision": decision.model_dump(),
            "report_json": self.render_measurement_json(result),
            "fallback_used": False,
        }
