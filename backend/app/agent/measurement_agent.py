from __future__ import annotations

import time

from backend.app.agent.state import MultiAgentState
from backend.app.schemas.measurement import MeasurementInput
from backend.app.services.measurement_service import MeasurementService


class MeasurementAgent:
    def __init__(self, measurement_service: MeasurementService | None = None) -> None:
        self.measurement_service = measurement_service or MeasurementService()

    def run(self, state: MultiAgentState, measurement: MeasurementInput) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "measurement_agent"

        result = self.measurement_service.analyze(measurement)
        state.measurement_report = result.model_dump()
        state.tool_results["body_measurement_analyzer"] = state.measurement_report
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
