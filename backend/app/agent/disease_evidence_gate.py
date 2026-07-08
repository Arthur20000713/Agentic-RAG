from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.agent.state import MultiAgentState


RAG_TOOL_NAME = "livestock_rag_search"
PARTIAL_SOURCE_URI_WARNING = "RAG_MAPPING_PARTIAL_SOURCE_URI"


@dataclass(frozen=True)
class DiseaseEvidenceGateResult:
    allowed: bool
    status: str
    evidence_refs: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_code: str | None = None


class DiseaseEvidenceGate:
    def evaluate(self, state: MultiAgentState) -> DiseaseEvidenceGateResult:
        rag_result = state.tool_results.get(RAG_TOOL_NAME)
        if not isinstance(rag_result, dict):
            return DiseaseEvidenceGateResult(allowed=False, status="missing", error_code="RAG_RESULT_MISSING")

        status = str(rag_result.get("status") or "missing")
        if status != "success":
            return DiseaseEvidenceGateResult(allowed=False, status=status, error_code="RAG_STATUS_NOT_SUCCESS")

        warnings = [str(item) for item in rag_result.get("mapping_warnings") or []]
        if PARTIAL_SOURCE_URI_WARNING in warnings:
            return DiseaseEvidenceGateResult(
                allowed=False,
                status=status,
                warnings=warnings,
                error_code="RAG_SOURCE_MAPPING_WARNING",
            )

        refs = self._valid_refs(rag_result)
        if not refs:
            return DiseaseEvidenceGateResult(
                allowed=False,
                status=status,
                warnings=warnings,
                error_code="RAG_VALID_EVIDENCE_MISSING",
            )

        return DiseaseEvidenceGateResult(allowed=True, status=status, evidence_refs=refs, warnings=warnings)

    def _valid_refs(self, rag_result: dict[str, Any]) -> list[dict[str, str]]:
        valid_hit_keys = {
            (str(hit["source_uri"]), str(hit["chunk_id"]))
            for hit in rag_result.get("hits") or []
            if isinstance(hit, dict) and hit.get("source_uri") and hit.get("chunk_id")
        }
        valid_citation_keys = {
            (str(citation["source_uri"]), str(citation["chunk_id"]))
            for citation in rag_result.get("citations") or []
            if isinstance(citation, dict) and citation.get("source_uri") and citation.get("chunk_id")
        }
        return [
            {"source_uri": source_uri, "chunk_id": chunk_id}
            for source_uri, chunk_id in sorted(valid_hit_keys & valid_citation_keys)
        ]
