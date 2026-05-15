from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote

from backend.app.schemas.rag_server import (
    RagCitation,
    RagDocumentSummary,
    RagSearchHit,
    RagSearchResult,
)


PARTIAL_SOURCE_URI_WARNING = "RAG_MAPPING_PARTIAL_SOURCE_URI"
SYNTHESIZED_CITATION_WARNING = "RAG_CITATION_SYNTHESIZED_FROM_HIT"


def build_source_uri(
    collection: str | None,
    doc_id: str | int | None,
    chunk_id: str | int | None,
    *,
    title: str | None = None,
    source: str | None = None,
    content: str | None = None,
    page: int | str | None = None,
    rank: int | None = None,
) -> str:
    resolved_collection = _uri_part(collection or "default")
    resolved_doc_id = doc_id
    resolved_chunk_id = chunk_id

    if resolved_doc_id in (None, ""):
        resolved_doc_id = f"unknown-doc-{_stable_digest(title, source, rank)}"
    if resolved_chunk_id in (None, ""):
        resolved_chunk_id = f"unknown-chunk-{_stable_digest(content, page, rank)}"

    return f"rag://{resolved_collection}/{_uri_part(resolved_doc_id)}/{_uri_part(resolved_chunk_id)}"


def _stable_digest(*parts: object) -> str:
    text = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _uri_part(value: object) -> str:
    return quote(str(value), safe="-_.~")


def _append_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


class RagServerMapper:
    @staticmethod
    def to_search_result(payload: dict[str, Any], *, query: str | None = None) -> RagSearchResult:
        mapping_warnings = list(payload.get("mapping_warnings") or [])
        if payload.get("isError") or payload.get("is_error"):
            return RagSearchResult(
                query=query or payload.get("query", ""),
                status="error",
                error_code=payload.get("error_code", "RAG_INTERNAL_ERROR"),
                error_message=payload.get("error_message", "rag server returned an error"),
                raw_response_id=payload.get("raw_response_id"),
                mapping_warnings=mapping_warnings,
            )

        status = payload.get("status", "success")
        raw_hits = payload.get("hits", payload.get("results", []))
        collection = payload.get("collection")
        hits: list[RagSearchHit] = []
        complete_source_flags: list[bool] = []
        for index, item in enumerate(raw_hits, start=1):
            has_partial_source = _has_partial_source(item)
            hit = RagServerMapper._to_hit(item, collection=collection, rank=index)
            hits.append(hit)
            complete_source_flags.append(not has_partial_source)
            if has_partial_source:
                _append_warning(mapping_warnings, PARTIAL_SOURCE_URI_WARNING)

        if not hits and status == "success":
            status = "empty"

        citations = [
            RagCitation.model_validate(item)
            for item in payload.get("citations", [])
        ]
        if not citations:
            citations = []
            for hit, has_complete_source in zip(hits, complete_source_flags):
                if not has_complete_source or not hit.source_uri:
                    continue
                citations.append(
                    RagCitation(
                        source_id=str(hit.document_id) if hit.document_id is not None else None,
                        source_uri=hit.source_uri,
                        title=hit.document_title,
                        page=hit.page,
                        section_title=hit.section_title,
                        chunk_id=hit.chunk_id,
                    )
                )
            if citations:
                _append_warning(mapping_warnings, SYNTHESIZED_CITATION_WARNING)

        return RagSearchResult(
            query=query or payload.get("query", ""),
            status=status,
            hits=hits,
            citations=citations,
            answer_text=payload.get("answer_text") or payload.get("answer"),
            raw_response_id=payload.get("raw_response_id"),
            mapping_warnings=mapping_warnings,
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
    def _to_hit(item: dict[str, Any], *, collection: str | None = None, rank: int | None = None) -> RagSearchHit:
        metadata = dict(item.get("metadata", {}))
        document_id = (
            item.get("doc_id")
            or item.get("document_id")
            or item.get("source_id")
            or metadata.get("doc_id")
            or metadata.get("document_id")
        )
        chunk_id = item.get("chunk_id") or item.get("id") or metadata.get("chunk_id", "")
        resolved_collection = item.get("collection") or metadata.get("collection") or collection
        title = (
            item.get("document_title")
            or item.get("title")
            or metadata.get("title")
            or "Unknown source"
        )
        content = item.get("content") or item.get("text") or ""
        source_uri = item.get("source_uri") or metadata.get("source_uri")
        resolved_document_id = document_id
        resolved_chunk_id = chunk_id
        if resolved_document_id in (None, ""):
            resolved_document_id = f"unknown-doc-{_stable_digest(title, metadata.get('source') or metadata.get('source_path'), rank)}"
        if resolved_chunk_id in (None, ""):
            resolved_chunk_id = f"unknown-chunk-{_stable_digest(content, item.get('page', metadata.get('page')), rank)}"
        if not source_uri:
            source_uri = build_source_uri(
                resolved_collection,
                document_id,
                chunk_id,
                title=title,
                source=metadata.get("source") or metadata.get("source_path"),
                content=content,
                page=item.get("page", metadata.get("page")),
                rank=rank,
            )
        return RagSearchHit(
            rank=item.get("rank") or rank,
            chunk_id=str(resolved_chunk_id),
            collection=resolved_collection,
            document_id=resolved_document_id,
            document_title=title,
            content=content,
            source_uri=source_uri,
            page=item.get("page", metadata.get("page")),
            section_title=item.get("section_title", metadata.get("section_title")),
            score=float(item.get("score", 0.0)),
            score_type=item.get("score_type", "rag_server_score"),
            raw_score=item.get("raw_score", metadata.get("raw_score")),
            mapped_score=item.get("mapped_score", metadata.get("mapped_score")),
            metadata=metadata,
        )


def _has_partial_source(item: dict[str, Any]) -> bool:
    metadata = dict(item.get("metadata", {}))
    doc_id = (
        item.get("doc_id")
        or item.get("document_id")
        or item.get("source_id")
        or metadata.get("doc_id")
        or metadata.get("document_id")
    )
    chunk_id = item.get("chunk_id") or item.get("id") or metadata.get("chunk_id")
    return doc_id in (None, "") or chunk_id in (None, "")
