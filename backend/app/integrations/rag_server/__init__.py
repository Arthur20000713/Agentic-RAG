from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient


def create_rag_server_client(settings: Settings) -> RagServerClient:
    if settings.rag_server.query_mode == "fake":
        return FakeRagServerClient()
    return RagServerMcpClient(settings)


__all__ = [
    "FakeRagServerClient",
    "RagServerClient",
    "RagServerMcpClient",
    "create_rag_server_client",
]

