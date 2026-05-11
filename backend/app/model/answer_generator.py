from __future__ import annotations

from backend.app.schemas.rag_server import RagCitation, RagSearchResult


NO_ANSWER_TEXT = "当前知识库中没有检索到足够依据，无法给出确定回答。建议补充更具体的信息，或咨询专业兽医/技术人员。"


class AnswerGenerator:
    def compose_with_citations(self, result: RagSearchResult) -> str:
        if not result.has_usable_hits:
            if result.status == "error":
                return f"当前 RAG-SERVER 调用失败，无法基于检索结果给出结论。错误信息：{result.error_message or result.error_code or 'unknown error'}"
            return NO_ANSWER_TEXT

        answer = result.answer_text or self._compose_from_hits(result)
        citations = self._format_citations(result.citations)
        if citations:
            return f"{answer}\n\n参考依据：\n{citations}"
        return answer

    def _compose_from_hits(self, result: RagSearchResult) -> str:
        first_hit = result.hits[0]
        return f"根据已检索到的资料，{first_hit.content}"

    def _format_citations(self, citations: list[RagCitation]) -> str:
        lines: list[str] = []
        for index, citation in enumerate(citations, start=1):
            location = ""
            if citation.page is not None:
                location = f"P{citation.page}"
            if citation.section_title:
                location = f"{location}，{citation.section_title}" if location else f"章节：{citation.section_title}"
            suffix = f"，{location}" if location else ""
            lines.append(f"[{index}] 《{citation.title}》{suffix}")
        return "\n".join(lines)

