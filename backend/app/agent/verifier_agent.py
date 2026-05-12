from __future__ import annotations

import time
from typing import Any

from backend.app.agent.state import MultiAgentState
from backend.app.agent.verifier import VerifierLite
from backend.app.schemas.agent import AgentToolError


RAG_TOOL_NAME = "livestock_rag_search"
PARTIAL_SOURCE_URI_WARNING = "RAG_MAPPING_PARTIAL_SOURCE_URI"


class VerifierAgent:
    def __init__(self, verifier: VerifierLite | None = None) -> None:
        self.verifier = verifier or VerifierLite()

    def verify(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "verifier_agent"

        answer = state.final_answer or state.draft_answer or ""
        citations = self._rag_citations(state)
        measurement_report = state.measurement_report or {}
        base_result = self.verifier.check(
            answer,
            require_citations=self._requires_citations(state),
            citations=citations,
            measurement_abnormal_items=measurement_report.get("abnormal_items"),
            measurement_evidence=measurement_report.get("evidence"),
        )

        citation_issues = self._citation_issues(state, base_result.issues)
        unsupported_claims = self._unsupported_claims(state, answer)
        issues = self._merge_issues(base_result.issues, citation_issues, unsupported_claims)
        result = {
            "passed": not issues,
            "issues": issues,
            "citation_issues": citation_issues,
            "unsupported_claims": unsupported_claims,
        }
        state.verification_result = result
        state.tool_results["verifier_agent"] = result
        for issue in issues:
            state.errors.append(AgentToolError(tool_name="verifier_agent", error_code=issue, message=issue))

        state.agent_trace.append(
            {
                "node": "verifier_agent",
                "status": "success" if result["passed"] else "failed",
                "passed": result["passed"],
                "issue_count": len(issues),
                "citation_issue_count": len(citation_issues),
                "unsupported_claim_count": len(unsupported_claims),
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    def _requires_citations(self, state: MultiAgentState) -> bool:
        if state.intent not in {"general_qa", "disease_consultation"}:
            return False
        rag_result = self._rag_result(state)
        return state.evidence_status == "success" and bool(rag_result.get("hits") or state.retrieved_contexts)

    def _rag_citations(self, state: MultiAgentState) -> list[dict[str, Any]]:
        return list(self._rag_result(state).get("citations") or [])

    def _rag_result(self, state: MultiAgentState) -> dict[str, Any]:
        value = state.tool_results.get(RAG_TOOL_NAME)
        return value if isinstance(value, dict) else {}

    def _citation_issues(self, state: MultiAgentState, base_issues: list[str]) -> list[str]:
        issues: list[str] = []
        if "missing_citation" in base_issues:
            issues.append("missing_citation")
        mapping_warnings = self._rag_result(state).get("mapping_warnings") or []
        if PARTIAL_SOURCE_URI_WARNING in mapping_warnings:
            issues.append("partial_source_uri")
        return issues

    def _unsupported_claims(self, state: MultiAgentState, answer: str) -> list[str]:
        if state.evidence_status not in {"empty", "low_confidence", "error"}:
            return []
        if not answer.strip() or self._is_fallback_answer(answer):
            return []
        if self._has_professional_claim(answer):
            return ["unsupported_claim"]
        return []

    def _has_professional_claim(self, answer: str) -> bool:
        claim_markers = [
            "应",
            "需要",
            "建议",
            "隔离",
            "联系兽医",
            "风险",
            "诊断",
            "处理",
            "资料显示",
            "可能与",
        ]
        return any(marker in answer for marker in claim_markers)

    def _is_fallback_answer(self, answer: str) -> bool:
        fallback_markers = [
            "没有检索到足够依据",
            "无法给出",
            "调用失败",
            "工具失败",
            "请先补充",
            "请补充",
            "超出畜牧业辅助问答范围",
        ]
        return any(marker in answer for marker in fallback_markers)

    def _merge_issues(
        self,
        base_issues: list[str],
        citation_issues: list[str],
        unsupported_claims: list[str],
    ) -> list[str]:
        merged: list[str] = []
        for issue in [*base_issues, *citation_issues, *unsupported_claims]:
            if issue not in merged:
                merged.append(issue)
        return merged
