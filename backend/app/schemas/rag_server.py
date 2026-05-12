from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RagResultStatus = Literal["success", "empty", "low_confidence", "error"]
RagScoreType = Literal["rag_server_score", "mapped_score", "unknown"]


class RagCitation(BaseModel):
    source_id: str | None = None
    source_uri: str | None = None
    title: str
    page: int | None = None
    section_title: str | None = None
    chunk_id: str | None = None


class RagSearchHit(BaseModel):
    rank: int | None = None
    chunk_id: str
    collection: str | None = None
    document_id: str | int | None = None
    document_title: str
    content: str
    source_uri: str | None = None
    page: int | None = None
    section_title: str | None = None
    score: float = 0.0
    score_type: RagScoreType = "rag_server_score"
    raw_score: float | None = None
    mapped_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagSearchResult(BaseModel):
    query: str
    status: RagResultStatus = "success"
    hits: list[RagSearchHit] = Field(default_factory=list)
    citations: list[RagCitation] = Field(default_factory=list)
    answer_text: str | None = None
    raw_response_id: str | None = None
    mapping_warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None

    @property
    def has_usable_hits(self) -> bool:
        return self.status == "success" and bool(self.hits)


class RagDocumentSummary(BaseModel):
    doc_id: str
    title: str | None = None
    summary: str
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    chunk_count: int | None = None
