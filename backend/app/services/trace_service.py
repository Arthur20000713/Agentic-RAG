from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.app.db.repositories import AgentTraceRepository, RagTraceRepository


class TraceService:
    def __init__(
        self,
        rag_trace_repository: RagTraceRepository,
        agent_trace_repository: AgentTraceRepository | None = None,
    ) -> None:
        self.rag_trace_repository = rag_trace_repository
        self.agent_trace_repository = agent_trace_repository

    def record_rag_call(
        self,
        *,
        rag_mode: str,
        status: str,
        session_id: str | None = None,
        request_id: str | None = None,
        collection: str | None = None,
        query: str | None = None,
        top_k: int | None = None,
        result_count: int | None = None,
        mapped_result_count: int | None = None,
        top_score: float | None = None,
        raw_response_id: str | None = None,
        error_code: str | None = None,
        latency_ms: int | None = None,
    ) -> str:
        resolved_raw_response_id = raw_response_id or f"rag_trace_{uuid4().hex}"
        self.rag_trace_repository.add(
            session_id=session_id,
            request_id=request_id,
            rag_mode=rag_mode,
            collection=collection,
            query=query,
            top_k=top_k,
            result_count=result_count,
            mapped_result_count=mapped_result_count,
            top_score=top_score,
            raw_response_id=resolved_raw_response_id,
            status=status,
            error_code=error_code,
            latency_ms=latency_ms,
        )
        return resolved_raw_response_id

    def record_agent_trace(
        self,
        *,
        trace: list[dict[str, Any]] | dict[str, Any],
        status: str,
        session_id: str | None = None,
        request_id: str | None = None,
        latency_ms: int | None = None,
        error_code: str | None = None,
    ) -> int:
        if self.agent_trace_repository is None:
            raise RuntimeError("agent trace repository is not configured")
        return self.agent_trace_repository.add(
            session_id=session_id,
            request_id=request_id,
            trace=trace,
            status=status,
            latency_ms=latency_ms,
            error_code=error_code,
        )

    def list_agent_traces(self, request_id: str) -> list[dict[str, Any]]:
        if self.agent_trace_repository is None:
            return []
        return self.agent_trace_repository.list_by_request_id(request_id)
