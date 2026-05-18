from __future__ import annotations

from abc import ABC, abstractmethod

from backend.app.schemas.rag_server import RagDocumentSummary, RagSearchResult


class RagServerClient(ABC):
    @abstractmethod
    async def query(
        self,
        query: str,
        *,
        top_k: int = 4,
        collection: str | None = None,
        domain: str | None = None,
        species: str | None = None,
        request_id: str | None = None,
    ) -> RagSearchResult:
        """Search the RAG-SERVER knowledge hub."""

    @abstractmethod
    async def get_document_summary(
        self,
        doc_id: str,
        *,
        collection: str | None = None,
    ) -> RagDocumentSummary:
        """Return a document summary from RAG-SERVER."""

    @abstractmethod
    async def list_collections(self, *, include_stats: bool = True) -> list[str]:
        """Return available RAG-SERVER collections."""
