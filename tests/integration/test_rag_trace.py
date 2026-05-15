from __future__ import annotations

from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import RagTraceRepository


def test_rag_trace_repository_persists_success_trace() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    traces = RagTraceRepository(conn)

    trace_id = traces.add(
        session_id="s1",
        request_id="req_1",
        rag_mode="real",
        collection="livestock_knowledge",
        query="calf diarrhea",
        top_k=5,
        result_count=2,
        mapped_result_count=2,
        top_score=0.82,
        raw_response_id="rag_trace_001",
        status="success",
        latency_ms=120,
        attempt_count=2,
    )

    row = traces.get(trace_id)

    assert row is not None
    assert row["request_id"] == "req_1"
    assert row["rag_mode"] == "real"
    assert row["collection"] == "livestock_knowledge"
    assert row["result_count"] == 2
    assert row["mapped_result_count"] == 2
    assert row["top_score"] == 0.82
    assert row["status"] == "success"
    assert row["error_code"] is None
    assert row["attempt_count"] == 2


def test_rag_trace_repository_persists_failed_and_fallback_traces() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    traces = RagTraceRepository(conn)

    failed_id = traces.add(
        session_id="s1",
        request_id="req_failure",
        rag_mode="real",
        collection="livestock_knowledge",
        query="calf diarrhea",
        top_k=5,
        result_count=0,
        mapped_result_count=0,
        status="failed",
        error_code="RAG_SERVER_TIMEOUT",
        latency_ms=5000,
    )
    fallback_id = traces.add(
        session_id="s1",
        request_id="req_failure",
        rag_mode="fake",
        collection="default",
        query="calf diarrhea",
        top_k=5,
        result_count=2,
        mapped_result_count=2,
        top_score=0.86,
        raw_response_id="fallback_fake",
        status="fallback",
        error_code="RAG_SERVER_PATH_NOT_CONFIGURED",
        latency_ms=3,
    )

    failed = traces.get(failed_id)
    fallback = traces.get(fallback_id)
    rows = traces.list_by_request_id("req_failure")

    assert failed is not None
    assert fallback is not None
    assert failed["status"] == "failed"
    assert failed["error_code"] == "RAG_SERVER_TIMEOUT"
    assert fallback["status"] == "fallback"
    assert fallback["error_code"] == "RAG_SERVER_PATH_NOT_CONFIGURED"
    assert [row["id"] for row in rows] == [failed_id, fallback_id]
