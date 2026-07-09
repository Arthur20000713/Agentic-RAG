from __future__ import annotations

import time
from typing import Any

from backend.app.agent.disease_understanding import DiseaseUnderstandingAgent
from backend.app.agent.disease_query_builder import DiseaseQueryBuilder
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings


class DiseaseAgent:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        primary_llm_client: Any | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.understanding_agent = DiseaseUnderstandingAgent(
            settings=self.settings,
            primary_llm_client=primary_llm_client,
        )
        self.query_builder = DiseaseQueryBuilder()

    def run(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "disease_agent"
        state.extracted_slots = {}

        self.understanding_agent.run(state)
        query_result = self.query_builder.build(state)
        state.rag_query = query_result.query
        state.tool_results["disease_query_builder"] = {
            "query": query_result.query,
            "facts": query_result.facts,
            "warnings": query_result.warnings,
        }
        gaps = _information_gaps(state)
        state.disease_assessment = {
            "status": "rag_ready",
            "reason": "disease consultation will be grounded in retrieved evidence and LLM reasoning",
            "follow_up_questions": [],
            "missing_info": [],
            "information_gaps": gaps,
        }
        state.draft_answer = "我会先检索畜牧资料，再结合检索证据分析；如果证据或现场信息不足，会在回答里说明需要继续确认的点。"
        self._append_trace(
            state,
            status="rag_ready",
            latency_ms=self._latency_ms(started_at),
            information_gap_count=len(gaps),
        )
        return state

    def _append_trace(
        self,
        state: MultiAgentState,
        *,
        status: str,
        latency_ms: int,
        information_gap_count: int = 0,
    ) -> None:
        state.agent_trace.append(
            {
                "node": "disease_agent",
                "status": status,
                "risk_level": None,
                "missing_info": [],
                "information_gap_count": information_gap_count,
                "latency_ms": latency_ms,
            }
        )

    def _latency_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))


def _information_gaps(state: MultiAgentState) -> list[str]:
    for key in ("disease_understanding", "disease_understanding_shadow"):
        record = state.tool_results.get(key)
        if isinstance(record, dict) and isinstance(record.get("understanding"), dict):
            gaps = record["understanding"].get("information_gaps")
            if isinstance(gaps, list):
                return [str(item) for item in gaps if str(item).strip()]
    return []
