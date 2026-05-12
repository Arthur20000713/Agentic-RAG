from __future__ import annotations

from typing import Any

from backend.app.schemas.rag_server import (
    RagCitation,
    RagDocumentSummary,
    RagSearchHit,
    RagSearchResult,
)


class RagServerMapper:
    @staticmethod
    def to_search_result(payload: dict[str, Any], *, query: str | None = None) -> RagSearchResult:
        if payload.get("isError") or payload.get("is_error"):
            return RagSearchResult(
                query=query or payload.get("query", ""),
                status="error",
                error_code=payload.get("error_code", "RAG_INTERNAL_ERROR"),
                error_message=payload.get("error_message", "rag server returned an error"),
                raw_response_id=payload.get("raw_response_id"),
                mapping_warnings=list(payload.get("mapping_warnings") or []),
            )

        status = payload.get("status", "success")
        raw_hits = payload.get("hits", payload.get("results", []))
        hits = [RagServerMapper._to_hit(item) for item in raw_hits]

        if not hits and status == "success":
            status = "empty"

        citations = [
            RagCitation.model_validate(item)
            for item in payload.get("citations", [])
        ]
        if not citations:
            citations = [
                RagCitation(
                    source_id=str(hit.document_id) if hit.document_id is not None else None,
                    source_uri=hit.source_uri,
                    title=hit.document_title,
                    page=hit.page,
                    section_title=hit.section_title,
                    chunk_id=hit.chunk_id,
                )
                for hit in hits
            ]

        return RagSearchResult(
            query=query or payload.get("query", ""),
            status=status,
            hits=hits,
            citations=citations,
            answer_text=payload.get("answer_text") or payload.get("answer"),
            raw_response_id=payload.get("raw_response_id"),
            mapping_warnings=list(payload.get("mapping_warnings") or []),
            error_code=payload.get("error_code"),
            error_message=payload.get("error_message"),
        )

    @staticmethod
    def to_document_summary(payload: dict[str, Any], *, doc_id: str | None = None) -> RagDocumentSummary:
        return RagDocumentSummary(
            doc_id=doc_id or payload.get("doc_id") or payload.get("document_id", ""),
            title=payload.get("title"),
            summary=payload.get("summary", ""),
            tags=list(payload.get("tags", [])),
            source=payload.get("source"),
            chunk_count=payload.get("chunk_count"),
        )

    @staticmethod
    def _to_hit(item: dict[str, Any]) -> RagSearchHit:
        metadata = dict(item.get("metadata", {}))
        document_id = item.get("document_id", item.get("source_id", metadata.get("document_id")))
        title = (
            item.get("document_title")
            or item.get("title")
            or metadata.get("title")
            or "Unknown source"
        )
        return RagSearchHit(
            rank=item.get("rank"),
            chunk_id=item.get("chunk_id") or item.get("id") or metadata.get("chunk_id", ""),
            collection=item.get("collection") or metadata.get("collection"),
            document_id=document_id,
            document_title=title,
            content=item.get("content") or item.get("text") or "",
            source_uri=item.get("source_uri") or metadata.get("source_uri"),
            page=item.get("page", metadata.get("page")),
            section_title=item.get("section_title", metadata.get("section_title")),
            score=float(item.get("score", 0.0)),
            score_type=item.get("score_type", "rag_server_score"),
            raw_score=item.get("raw_score", metadata.get("raw_score")),
            mapped_score=item.get("mapped_score", metadata.get("mapped_score")),
            metadata=metadata,
        )
