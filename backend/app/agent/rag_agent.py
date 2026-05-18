from __future__ import annotations

import time

from backend.app.agent.state import MultiAgentState
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.schemas.agent import AgentToolError, RetrievedContext
from backend.app.schemas.rag_server import RagSearchResult


TOOL_NAME = "livestock_rag_search"


class RagAgent:
    def __init__(
        self,
        rag_client: RagServerClient | None = None,
        *,
        top_k: int = 4,
        collection: str | None = None,
    ) -> None:
        self.rag_client = rag_client or FakeRagServerClient()
        self.top_k = top_k
        self.collection = collection

    async def run(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        query = self._resolve_query(state)
        state.rag_query = query
        state.active_agent = "rag_agent"

        try:
            result = await self.rag_client.query(
                query,
                top_k=self.top_k,
                collection=self.collection,
                request_id=state.request_id,
            )
        except Exception as exc:
            latency_ms = self._latency_ms(started_at)
            self._record_exception(state, query=query, exc=exc, latency_ms=latency_ms)
            return state

        state.tool_results[TOOL_NAME] = result.model_dump()
        state.evidence_status = result.status
        self._attach_hits(state, result)
        if result.status == "error":
            state.errors.append(
                AgentToolError(
                    tool_name="rag_agent",
                    error_code=result.error_code or "RAG_ERROR",
                    message=result.error_message or "RAG query failed",
                )
            )
        self._append_trace(
            state,
            status=result.status,
            query=query,
            result_count=len(result.hits),
            latency_ms=self._latency_ms(started_at),
            error_code=result.error_code,
        )
        return state

    def _resolve_query(self, state: MultiAgentState) -> str:
        return (state.rag_query or state.normalized_query or state.user_query).strip()

    def _attach_hits(self, state: MultiAgentState, result: RagSearchResult) -> None:
        for hit in result.hits:
            state.retrieved_contexts.append(
                RetrievedContext(
                    chunk_id=hit.chunk_id,
                    document_id=hit.document_id,
                    title=hit.document_title,
                    content=hit.content,
                    page=hit.page,
                    section_title=hit.section_title,
                    score=hit.score,
                    source_type=hit.metadata.get("source_type"),
                )
            )

    def _record_exception(self, state: MultiAgentState, *, query: str, exc: Exception, latency_ms: int) -> None:
        error_code = "RAG_AGENT_EXCEPTION"
        error_message = str(exc) or exc.__class__.__name__
        state.evidence_status = "error"
        state.tool_results[TOOL_NAME] = {
            "query": query,
            "status": "error",
            "hits": [],
            "citations": [],
            "answer_text": None,
            "raw_response_id": None,
            "mapping_warnings": [],
            "error_code": error_code,
            "error_message": error_message,
        }
        state.errors.append(AgentToolError(tool_name="rag_agent", error_code=error_code, message=error_message))
        self._append_trace(
            state,
            status="error",
            query=query,
            result_count=0,
            latency_ms=latency_ms,
            error_code=error_code,
        )

    def _append_trace(
        self,
        state: MultiAgentState,
        *,
        status: str,
        query: str,
        result_count: int,
        latency_ms: int,
        error_code: str | None = None,
    ) -> None:
        state.agent_trace.append(
            {
                "node": "rag_agent",
                "status": status,
                "evidence_status": state.evidence_status,
                "query": query,
                "result_count": result_count,
                "error_code": error_code,
                "latency_ms": latency_ms,
            }
        )

    def _latency_ms(self, started_at: float) -> int:
        return max(0, int((time.perf_counter() - started_at) * 1000))
