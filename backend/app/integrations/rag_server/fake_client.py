from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.mapper import RagServerMapper
from backend.app.schemas.rag_server import RagDocumentSummary, RagSearchResult


class FakeRagServerClient(RagServerClient):
    def __init__(self, fixture_dir: str | Path | None = None) -> None:
        self.fixture_dir = Path(fixture_dir) if fixture_dir else PROJECT_ROOT / "tests" / "fixtures" / "rag_server"

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
        fixture_name = self._select_query_fixture(query)
        payload = self._load_json(fixture_name)
        result = RagServerMapper.to_search_result(
            payload,
            query=query,
            min_mapped_score=0.0,
            min_citation_count_for_answer=0,
            low_confidence_no_answer=False,
        )
        if top_k > 0:
            result.hits = result.hits[:top_k]
            result.citations = result.citations[:top_k]
        return result

    async def get_document_summary(
        self,
        doc_id: str,
        *,
        collection: str | None = None,
    ) -> RagDocumentSummary:
        payload = self._load_json("document_summary.json")
        return RagServerMapper.to_document_summary(payload, doc_id=doc_id)

    async def list_collections(self, *, include_stats: bool = True) -> list[str]:
        return ["default", "test"]

    def _select_query_fixture(self, query: str) -> str:
        normalized = query.lower()
        if "timeout" in normalized or "失败" in normalized or "error" in normalized:
            return "error_response.json"
        if "没有答案" in normalized or "unknown" in normalized or "empty" in normalized:
            return "empty_response.json"
        if "低置信" in normalized or "low confidence" in normalized:
            return "low_confidence_response.json"
        return "query_response.json"

    def _load_json(self, name: str) -> dict:
        path = self.fixture_dir / name
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
