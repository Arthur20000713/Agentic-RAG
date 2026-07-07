from __future__ import annotations

import re

from backend.app.schemas.rag_server import RagCitation, RagSearchResult


NO_ANSWER_TEXT = "当前知识库中没有检索到足够依据，无法给出确定回答。建议补充更具体的信息，或咨询专业兽医/技术人员。"


class AnswerGenerator:
    def compose_with_citations(self, result: RagSearchResult) -> str:
        if not result.has_usable_hits:
            if result.status == "error":
                return f"当前 RAG-SERVER 调用失败，无法基于检索结果给出结论。错误信息：{result.error_message or result.error_code or 'unknown error'}"
            return NO_ANSWER_TEXT

        answer = self._natural_answer_text(result) or self._compose_from_hits(result)
        citations = self._format_citations(result.citations)
        if citations:
            return f"{answer}\n\n参考依据：\n{citations}"
        return answer

    def _natural_answer_text(self, result: RagSearchResult) -> str | None:
        if not result.answer_text:
            return None
        answer = result.answer_text.strip()
        if not answer or self._looks_like_retrieval_dump(answer):
            return None
        return answer

    def _looks_like_retrieval_dump(self, text: str) -> bool:
        normalized = text.lstrip().lower()
        if normalized.startswith(("## query results", "# query results", "## 检索结果", "# 检索结果")):
            return True
        dump_markers = ("### result", "score:", "source:", "chunk_id", "document_id")
        return sum(1 for marker in dump_markers if marker in normalized) >= 2

    def _compose_from_hits(self, result: RagSearchResult) -> str:
        snippets = [snippet for hit in result.hits[:3] if (snippet := self._clean_snippet(hit.content))]
        if not snippets:
            return "根据已检索到的资料，暂时只能确认存在相关来源，但没有可用于回答的文本片段。"
        if len(snippets) == 1:
            return f"根据已检索到的资料，{snippets[0]}"
        lines = "\n".join(f"- {snippet}" for snippet in snippets)
        return f"根据已检索到的资料，可归纳为：\n{lines}"

    def _clean_snippet(self, text: str) -> str:
        snippet = re.sub(r"\s+", " ", text).strip()
        snippet = re.sub(r"^#+\s*", "", snippet)
        if len(snippet) > 220:
            return f"{snippet[:220].rstrip()}..."
        return snippet

    def _format_citations(self, citations: list[RagCitation]) -> str:
        lines: list[str] = []
        for index, citation in enumerate(citations, start=1):
            location = ""
            if citation.page is not None:
                location = f"P{citation.page}"
            if citation.section_title:
                location = f"{location}，{citation.section_title}" if location else f"章节：{citation.section_title}"
            suffix = f"，{location}" if location else ""
            source_uri = f"，{citation.source_uri}" if citation.source_uri else ""
            lines.append(f"[{index}] 《{citation.title}》{suffix}{source_uri}")
        return "\n".join(lines)
