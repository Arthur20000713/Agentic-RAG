from __future__ import annotations

import re
import time
from typing import Any

from pydantic import BaseModel

from backend.app.agent.rag_answer_policy import (
    NO_ANSWER_POLICY_WARNING,
    NO_ANSWER_TEXT,
    SAFETY_REFUSAL_POLICY_WARNING,
)
from backend.app.agent.state import MultiAgentState
from backend.app.agent.verifier import VerifierLite
from backend.app.schemas.agent import AgentToolError

RAG_TOOL_NAME = "livestock_rag_search"
PARTIAL_SOURCE_URI_WARNING = "RAG_MAPPING_PARTIAL_SOURCE_URI"


class ClaimCheck(BaseModel):
    claim: str
    source_uri: str | None = None
    supported: bool
    issue: str | None = None


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
        base_issues = list(base_result.issues)
        if state.intent != "disease_consultation":
            base_issues = [
                issue
                for issue in base_issues
                if issue not in {"dosage", "prescription", "definitive_diagnosis"}
            ]

        citation_issues = self._citation_issues(state, answer, base_issues)
        unsupported_claims = self._unsupported_claims(state, answer)
        claim_checks = self._claim_checks(state, answer)
        claim_issues = [check.issue for check in claim_checks if not check.supported and check.issue]
        disease_reasoning_issues = self._disease_reasoning_issues(state)
        issues = self._merge_issues(
            base_issues,
            citation_issues,
            unsupported_claims,
            claim_issues,
            disease_reasoning_issues,
        )
        result = {
            "passed": not issues,
            "issues": issues,
            "citation_issues": citation_issues,
            "unsupported_claims": unsupported_claims,
            "claim_checks": [check.model_dump() for check in claim_checks],
            "disease_reasoning_issues": disease_reasoning_issues,
        }
        state.verification_result = result
        state.tool_results["verifier_agent"] = result
        for issue in issues:
            state.errors.append(AgentToolError(tool_name="verifier_agent", error_code=issue, message=issue))
        if self._must_fail_closed(state, issues):
            state.draft_answer = NO_ANSWER_TEXT
            state.final_answer = None
            state.evidence_status = "low_confidence"
            state.retrieved_contexts.clear()

        state.agent_trace.append(
            {
                "node": "verifier_agent",
                "status": "success" if result["passed"] else "failed",
                "passed": result["passed"],
                "issue_count": len(issues),
                "citation_issue_count": len(citation_issues),
                "unsupported_claim_count": len(unsupported_claims),
                "claim_check_count": len(claim_checks),
                "disease_reasoning_issue_count": len(disease_reasoning_issues),
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state

    def _requires_citations(self, state: MultiAgentState) -> bool:
        if state.intent not in {"general_qa", "disease_consultation"}:
            return False
        if self._rag_answer_policy_blocks_sources(state):
            return False
        rag_result = self._rag_result(state)
        return state.evidence_status == "success" and bool(rag_result.get("hits") or state.retrieved_contexts)

    def _rag_citations(self, state: MultiAgentState) -> list[dict[str, Any]]:
        return list(self._rag_result(state).get("citations") or [])

    def _rag_result(self, state: MultiAgentState) -> dict[str, Any]:
        value = state.tool_results.get(RAG_TOOL_NAME)
        return value if isinstance(value, dict) else {}

    def _rag_answer_policy_blocks_sources(self, state: MultiAgentState) -> bool:
        policy = state.tool_results.get("rag_answer_policy")
        if not isinstance(policy, dict):
            return False
        return policy.get("warning") in {NO_ANSWER_POLICY_WARNING, SAFETY_REFUSAL_POLICY_WARNING}

    def _citation_issues(self, state: MultiAgentState, answer: str, base_issues: list[str]) -> list[str]:
        issues: list[str] = []
        if "missing_citation" in base_issues:
            issues.append("missing_citation")
        if self._requires_citations(state) and self._rag_citations(state):
            indexes = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
            citation_count = len(self._rag_citations(state))
            if not indexes:
                issues.append("answer_missing_citation_marker")
            elif any(index < 1 or index > citation_count for index in indexes):
                issues.append("citation_index_out_of_range")
        mapping_warnings = self._rag_result(state).get("mapping_warnings") or []
        if self._requires_citations(state) and PARTIAL_SOURCE_URI_WARNING in mapping_warnings:
            issues.append("partial_source_uri")
        return issues

    def _unsupported_claims(self, state: MultiAgentState, answer: str) -> list[str]:
        if state.intent not in {"general_qa", "disease_consultation"}:
            return []
        if self._is_reference_only_answer(state) or self._is_structured_no_answer(state):
            return []
        if state.evidence_status not in {"empty", "low_confidence", "error"}:
            return []
        if not answer.strip() or self._is_fallback_answer(answer):
            return []
        if self._has_professional_claim(answer):
            return ["unsupported_claim"]
        return []

    def _claim_checks(self, state: MultiAgentState, answer: str) -> list[ClaimCheck]:
        if state.intent not in {"general_qa", "disease_consultation"}:
            return []
        if self._is_reference_only_answer(state) or self._is_structured_no_answer(state):
            return []
        if self._rag_answer_policy_blocks_sources(state):
            return []
        if not answer.strip() or self._is_fallback_answer(answer):
            return []

        source_uris = self._source_uris(state)
        claim = self._claim_text(answer)
        if source_uris:
            supported = self._claim_supported_by_evidence(claim, state)
            if supported is False:
                return [
                    ClaimCheck(
                        claim=claim,
                        source_uri=source_uris[0],
                        supported=False,
                        issue="claim_not_supported_by_evidence",
                    )
                ]
            return [ClaimCheck(claim=claim, source_uri=source_uris[0], supported=True)]
        return [ClaimCheck(claim=claim, supported=False, issue="claim_missing_source_uri")]

    def _is_reference_only_answer(self, state: MultiAgentState) -> bool:
        record = state.tool_results.get("grounded_answer_agent")
        return isinstance(record, dict) and record.get("reference_only") is True

    def _is_structured_no_answer(self, state: MultiAgentState) -> bool:
        record = state.tool_results.get("grounded_answer_agent")
        if isinstance(record, dict) and record.get("status") == "no_answer":
            return True
        retrieval = state.agentic_retrieval
        return retrieval is not None and retrieval.final_status == "insufficient"

    def _claim_supported_by_evidence(self, claim: str, state: MultiAgentState) -> bool | None:
        claim_tokens = self._english_claim_tokens(claim)
        if len(claim_tokens) < 2:
            return None
        evidence_tokens: set[str] = set()
        for hit in self._rag_result(state).get("hits") or []:
            if isinstance(hit, dict):
                evidence_tokens.update(self._english_claim_tokens(str(hit.get("content") or "")))
        if len(evidence_tokens) < 2:
            for context in state.retrieved_contexts:
                evidence_tokens.update(self._english_claim_tokens(context.content))
        if len(evidence_tokens) < 2:
            return None
        return bool(claim_tokens & evidence_tokens)

    def _english_claim_tokens(self, text: str) -> set[str]:
        stopwords = {
            "a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from",
            "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with",
        }
        return {
            token
            for token in re.findall(r"[a-z]{3,}", text.lower())
            if token not in stopwords
        }

    def _must_fail_closed(self, state: MultiAgentState, issues: list[str]) -> bool:
        if state.intent not in {"general_qa", "disease_consultation"} or state.evidence_status != "success":
            return False
        safety_violations = set(
            self.verifier.safety_guard.check(state.final_answer or state.draft_answer or "").violations
        )
        if safety_violations.intersection({"dosage", "prescription", "definitive_diagnosis"}):
            return False
        blocking = {
            "missing_citation",
            "answer_missing_citation_marker",
            "citation_index_out_of_range",
            "claim_missing_source_uri",
            "claim_not_supported_by_evidence",
        }
        return bool(blocking.intersection(issues))

    def _source_uris(self, state: MultiAgentState) -> list[str]:
        source_uris: list[str] = []
        rag_result = self._rag_result(state)
        for citation in rag_result.get("citations") or []:
            if isinstance(citation, dict) and citation.get("source_uri"):
                source_uris.append(str(citation["source_uri"]))
        for hit in rag_result.get("hits") or []:
            if isinstance(hit, dict) and hit.get("source_uri"):
                source_uris.append(str(hit["source_uri"]))
        return source_uris

    def _claim_text(self, answer: str) -> str:
        first_line = next((line.strip() for line in answer.splitlines() if line.strip()), "")
        return first_line[:240]

    def _disease_reasoning_issues(self, state: MultiAgentState) -> list[str]:
        if state.intent != "disease_consultation":
            return []
        reasoning = self._disease_reasoning_payload(state)
        if reasoning is None:
            return []

        issues: list[str] = []
        allowed_refs = self._allowed_disease_refs(state)
        for item in self._disease_reasoning_items(reasoning):
            text = str(item.get("text") or "")
            refs = item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else []
            if not refs:
                issues.append("disease_reasoning_missing_evidence_ref")
            for ref in refs:
                if not isinstance(ref, dict):
                    issues.append("disease_reasoning_missing_evidence_ref")
                    continue
                key = (str(ref.get("source_uri")), str(ref.get("chunk_id")))
                if key not in allowed_refs:
                    issues.append("disease_reasoning_ref_outside_gate")
            safety = self.verifier.safety_guard.check(text)
            if safety.violations:
                issues.append("disease_reasoning_safety_violation")
        return self._dedupe(issues)

    def _disease_reasoning_payload(self, state: MultiAgentState) -> dict[str, Any] | None:
        for key in ("disease_reasoning", "disease_reasoning_shadow"):
            record = state.tool_results.get(key)
            if isinstance(record, dict) and record.get("status") == "success" and isinstance(record.get("reasoning"), dict):
                return record["reasoning"]
        return None

    def _allowed_disease_refs(self, state: MultiAgentState) -> set[tuple[str, str]]:
        gate = state.tool_results.get("disease_evidence_gate")
        if not isinstance(gate, dict) or not gate.get("allowed"):
            return set()
        return {
            (str(ref.get("source_uri")), str(ref.get("chunk_id")))
            for ref in gate.get("evidence_refs") or []
            if isinstance(ref, dict) and ref.get("source_uri") and ref.get("chunk_id")
        }

    def _disease_reasoning_items(self, reasoning: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for section in ("contributing_factors", "safe_actions", "vet_triggers"):
            values = reasoning.get(section) or []
            if isinstance(values, list):
                items.extend([item for item in values if isinstance(item, dict)])
        return items

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
        claim_issues: list[str | None],
        disease_reasoning_issues: list[str] | None = None,
    ) -> list[str]:
        merged: list[str] = []
        for issue in [
            *base_issues,
            *citation_issues,
            *unsupported_claims,
            *claim_issues,
            *(disease_reasoning_issues or []),
        ]:
            if issue is None:
                continue
            if issue not in merged:
                merged.append(issue)
        return merged

    def _dedupe(self, issues: list[str]) -> list[str]:
        deduped: list[str] = []
        for issue in issues:
            if issue not in deduped:
                deduped.append(issue)
        return deduped
