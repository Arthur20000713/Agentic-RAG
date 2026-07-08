from __future__ import annotations

import time
from typing import Any

from backend.app.agent.rag_answer_policy import NO_ANSWER_POLICY_WARNING, SAFETY_REFUSAL_POLICY_WARNING
from backend.app.agent.state import MultiAgentState


RAG_TOOL_NAME = "livestock_rag_search"


class ResponseAgent:
    def render(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "response_agent"

        safe_answer = self._safe_answer(state)
        sources = self._sources(state)
        final_answer = self._render_answer(
            safe_answer,
            sources,
            safety_passed=self._safety_passed(state),
        )
        state.final_answer = final_answer

        previous_tools = [tool for tool in state.tool_results if tool != "response_agent"]
        response_payload = {
            "answer": final_answer,
            "safe_answer": safe_answer,
            "sources": sources,
            "tools_used": [*previous_tools, "response_agent"],
            "intent": state.intent,
            "evidence_status": state.evidence_status,
            "safety_result": state.safety_result,
            "verification_result": state.verification_result,
            "errors": [error.model_dump() for error in state.errors],
        }
        state.tool_results["response_agent"] = response_payload
        state.agent_trace.append(
            {
                "node": "response_agent",
                "status": "success",
                "source_count": len(sources),
                "tool_count": len(response_payload["tools_used"]),
                "answer_length": len(final_answer),
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    def _safe_answer(self, state: MultiAgentState) -> str:
        if isinstance(state.safety_result, dict):
            safe_answer = state.safety_result.get("safe_answer")
            if isinstance(safe_answer, str) and safe_answer.strip():
                return safe_answer
        if state.final_answer:
            return state.final_answer
        if state.draft_answer:
            return state.draft_answer
        return "当前无法生成回答，请稍后重试或补充问题信息。"

    def _sources(self, state: MultiAgentState) -> list[dict[str, Any]]:
        if self._rag_answer_policy_blocks_sources(state):
            return []

        rag_result = self._rag_result(state)
        if state.evidence_status != "success" or rag_result.get("status") != "success":
            return []

        hits = list(rag_result.get("hits") or [])
        sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for citation in rag_result.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            hit = self._matching_hit(citation, hits)
            source_uri = citation.get("source_uri") or (hit or {}).get("source_uri")
            key = source_uri or "|".join(
                str(citation.get(field) or "")
                for field in ("source_id", "chunk_id", "title", "page")
            )
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "source_uri": source_uri,
                    "source_id": citation.get("source_id"),
                    "title": citation.get("title") or (hit or {}).get("document_title"),
                    "page": citation.get("page"),
                    "section_title": citation.get("section_title"),
                    "chunk_id": citation.get("chunk_id") or (hit or {}).get("chunk_id"),
                }
            )
        return sources

    def _matching_hit(self, citation: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any] | None:
        chunk_id = citation.get("chunk_id")
        if chunk_id:
            for hit in hits:
                if hit.get("chunk_id") == chunk_id:
                    return hit

        source_id = citation.get("source_id")
        title = citation.get("title")
        for hit in hits:
            if source_id is not None and str(hit.get("document_id")) == str(source_id):
                return hit
            if title and hit.get("document_title") == title:
                return hit
        return None

    def _render_answer(
        self,
        safe_answer: str,
        sources: list[dict[str, Any]],
        *,
        safety_passed: bool,
    ) -> str:
        if not sources or not safety_passed:
            return safe_answer
        if "参考依据" in safe_answer or "参考来源" in safe_answer or "[1]" in safe_answer:
            return safe_answer
        return f"{safe_answer}\n\n参考来源：\n{self._format_sources(sources)}"

    def _format_sources(self, sources: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for index, source in enumerate(sources, start=1):
            title = source.get("title") or "未知来源"
            location = ""
            if source.get("page") is not None:
                location = f"P{source['page']}"
            if source.get("section_title"):
                location = f"{location}，{source['section_title']}" if location else str(source["section_title"])
            source_uri = source.get("source_uri")
            suffix = f"，{location}" if location else ""
            uri_suffix = f"，{source_uri}" if source_uri else ""
            lines.append(f"[{index}] 《{title}》{suffix}{uri_suffix}")
        return "\n".join(lines)

    def _safety_passed(self, state: MultiAgentState) -> bool:
        if not isinstance(state.safety_result, dict):
            return True
        return bool(state.safety_result.get("passed", True))

    def _rag_answer_policy_blocks_sources(self, state: MultiAgentState) -> bool:
        policy = state.tool_results.get("rag_answer_policy")
        if not isinstance(policy, dict):
            return False
        return policy.get("warning") in {NO_ANSWER_POLICY_WARNING, SAFETY_REFUSAL_POLICY_WARNING}

    def _rag_result(self, state: MultiAgentState) -> dict[str, Any]:
        value = state.tool_results.get(RAG_TOOL_NAME)
        return value if isinstance(value, dict) else {}
