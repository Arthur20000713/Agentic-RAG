from __future__ import annotations

import time
from typing import Any

from backend.app.agent.router import IntentRouter, RouteResult
from backend.app.agent.state import MultiAgentState
from backend.app.agent.task_planner import PLANNED_INTENTS, TaskPlanner
from backend.app.core.config import Settings
from backend.app.model.intent_router import IntentRoutingResult


ACTIVE_AGENT_BY_INTENT = {
    "assistant_intro": "response_agent",
    "general_qa": "rag_agent",
    "disease_consultation": "disease_agent",
    "measurement_analysis": "measurement_agent",
    "out_of_scope": "response_agent",
}


class SupervisorAgent:
    def __init__(self, router: IntentRouter | None = None) -> None:
        self.router = router or IntentRouter()

    def route(self, state: MultiAgentState, *, route_override: IntentRoutingResult | None = None) -> MultiAgentState:
        started_at = time.perf_counter()
        result = route_override or self.router.route(state.user_query)
        route_source = "model" if route_override is not None else "rule"
        state.normalized_query = state.normalized_query or state.user_query.strip()
        state.intent = result.intent
        state.route_reason = result.reason
        state.active_agent = ACTIVE_AGENT_BY_INTENT[result.intent]
        supervisor_result = {
            "intent": result.intent,
            "confidence": result.confidence,
            "reason": result.reason,
            "route_source": route_source,
        }
        state.tool_results["supervisor"] = supervisor_result
        if route_override is not None:
            state.tool_results["intent_router_model"] = route_override.model_dump()
        self._append_trace(
            state,
            result,
            route_source=route_source,
            latency_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
        )
        return state

    async def plan(
        self,
        state: MultiAgentState,
        *,
        settings: Settings | None = None,
        primary_llm_client: Any | None = None,
    ) -> MultiAgentState:
        if state.intent not in PLANNED_INTENTS:
            state.task_plan = None
            return state

        started_at = time.perf_counter()
        outcome = await TaskPlanner(
            settings=settings,
            primary_llm_client=primary_llm_client,
        ).plan(state)
        state.task_plan = outcome.plan
        retrieval = next(
            step for step in outcome.plan.steps if step.action == "query_knowledge_hub"
        )
        query_source = str(retrieval.arguments["query_source"])
        query = getattr(state, query_source, None) or state.normalized_query or state.user_query
        state.tool_plan = [
            {
                "tool": "query_knowledge_hub",
                "arguments": {
                    "query": str(query).strip(),
                    "top_k": int(retrieval.arguments["top_k"]),
                },
            }
        ]
        state.agent_trace.append(
            {
                "node": "planner",
                "status": "fallback" if outcome.fallback_used else "success",
                "plan_id": outcome.plan.plan_id,
                "revision": outcome.plan.revision,
                "source": outcome.plan.source,
                "step_count": len(outcome.plan.steps),
                "fallback_used": outcome.fallback_used,
                "fallback_reason": outcome.fallback_reason,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    def _append_trace(
        self,
        state: MultiAgentState,
        result: RouteResult | IntentRoutingResult,
        *,
        route_source: str,
        latency_ms: int,
    ) -> None:
        state.agent_trace.append(
            {
                "node": "supervisor",
                "status": "success",
                "intent": result.intent,
                "active_agent": ACTIVE_AGENT_BY_INTENT[result.intent],
                "route_reason": result.reason,
                "confidence": result.confidence,
                "route_source": route_source,
                "latency_ms": latency_ms,
            }
        )
