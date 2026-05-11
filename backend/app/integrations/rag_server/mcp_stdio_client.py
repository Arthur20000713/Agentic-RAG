from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.rag_server import RagDocumentSummary, RagSearchResult


class RagServerMcpClient(RagServerClient):
    """Placeholder boundary for the real MCP stdio client.

    The fake client is the default V1 test path. Real MCP process lifecycle and
    JSON-RPC calls are intentionally isolated here for a later C7/C8 increment.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def query(
        self,
        query: str,
        *,
        top_k: int = 4,
        collection: str | None = None,
        domain: str | None = None,
        species: str | None = None,
    ) -> RagSearchResult:
        return RagSearchResult(
            query=query,
            status="error",
            error_code="RAG_MCP_NOT_IMPLEMENTED",
            error_message="real MCP stdio client is not implemented in this increment",
        )

    async def get_document_summary(
        self,
        doc_id: str,
        *,
        collection: str | None = None,
    ) -> RagDocumentSummary:
        return RagDocumentSummary(
            doc_id=doc_id,
            summary="real MCP stdio client is not implemented in this increment",
        )

    async def list_collections(self, *, include_stats: bool = True) -> list[str]:
        return []

