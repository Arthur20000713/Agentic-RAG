from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient
from backend.app.services.trace_service import TraceService


def create_rag_server_client(settings: Settings, trace_service: TraceService | None = None) -> RagServerClient:
    if not settings.rag_server.uses_real_rag_server:
        return FakeRagServerClient()
    return RagServerMcpClient(settings, trace_service=trace_service)


__all__ = [
    "FakeRagServerClient",
    "RagServerClient",
    "RagServerMcpClient",
    "create_rag_server_client",
]
