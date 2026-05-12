from __future__ import annotations

import time

from backend.app.agent.router import IntentRouter, RouteResult
from backend.app.agent.state import MultiAgentState


ACTIVE_AGENT_BY_INTENT = {
    "general_qa": "rag_agent",
    "disease_consultation": "disease_agent",
    "measurement_analysis": "measurement_agent",
    "out_of_scope": "response_agent",
}


class SupervisorAgent:
    def __init__(self, router: IntentRouter | None = None) -> None:
        self.router = router or IntentRouter()

    def route(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        result = self.router.route(state.user_query)
        state.normalized_query = state.normalized_query or state.user_query.strip()
        state.intent = result.intent
        state.route_reason = result.reason
        state.active_agent = ACTIVE_AGENT_BY_INTENT[result.intent]
        state.tool_results["supervisor"] = result.model_dump()
        self._append_trace(state, result, latency_ms=max(0, int((time.perf_counter() - started_at) * 1000)))
        return state

    def _append_trace(self, state: MultiAgentState, result: RouteResult, *, latency_ms: int) -> None:
        state.agent_trace.append(
            {
                "node": "supervisor",
                "status": "success",
                "intent": result.intent,
                "active_agent": ACTIVE_AGENT_BY_INTENT[result.intent],
                "route_reason": result.reason,
                "confidence": result.confidence,
                "latency_ms": latency_ms,
            }
        )
