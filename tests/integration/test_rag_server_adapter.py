from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import RagTraceRepository
from backend.app.integrations.rag_server import create_rag_server_client
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient
from backend.app.services.trace_service import TraceService


def test_real_rag_adapter_is_created_with_trace_service() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    trace_service = TraceService(RagTraceRepository(conn))
    settings = Settings(rag_server={"query_mode": "real", "repo_path": "."})

    client = create_rag_server_client(settings, trace_service=trace_service)

    assert isinstance(client, RagServerMcpClient)
    assert client.trace_service is trace_service
