from __future__ import annotations

from uuid import uuid4

from backend.app.db.repositories import RagTraceRepository


class TraceService:
    def __init__(self, rag_trace_repository: RagTraceRepository) -> None:
        self.rag_trace_repository = rag_trace_repository

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
