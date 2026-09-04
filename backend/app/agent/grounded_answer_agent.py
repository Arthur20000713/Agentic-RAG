from __future__ import annotations

import re
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.rag_answer_policy import (
    NO_ANSWER_TEXT,
    build_insufficient_evidence_answer,
)
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.answer_generator import AnswerGenerator
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest
from backend.app.schemas.rag_server import RagSearchResult

RAG_TOOL_NAME = "livestock_rag_search"
_NON_SUBSTANTIVE_QUERY_TOKENS = {
    "a",
    "an",
    "base",
    "cattle",
    "empty",
    "knowledge",
    "livestock",
    "question",
    "the",
}


class GroundedAnswerPayload(BaseModel):
    status: Literal["success"]
    schema_name: str = "grounded_rag_answer"
    answer_draft: str = Field(min_length=1)
    evidence_sufficient: bool = True
    fallback_required: bool = False
    reason: str | None = None


class ReferenceOnlyAnswerPayload(BaseModel):
    status: Literal["success"]
    answer_draft: str = Field(min_length=1)
    fallback_required: bool = False
    reason: str | None = None


class GroundedAnswerAgent:
    def __init__(self, settings: Settings | None = None, primary_llm_client: Any | None = None) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    async def run(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "grounded_answer_agent"
        rag_result = self._rag_result(state)

        retrieval = state.agentic_retrieval
        if retrieval is not None and retrieval.final_status == "insufficient":
            final_grade = retrieval.grades[-1] if retrieval.grades else None
            self._discard_agentic_evidence(state)
            self._use_no_answer(
                state,
                status="no_answer",
                fallback_reason=retrieval.termination_code or "agentic_retrieval_insufficient",
                started_at=started_at,
                answer_text=build_insufficient_evidence_answer(
                    state.user_query,
                    missing_aspects=list(final_grade.missing_aspects) if final_grade else [],
                    has_conflicts=bool(final_grade and final_grade.conflicts),
                ),
            )
            return state

        if rag_result is not None and rag_result.status in {"empty", "low_confidence"}:
            if await self._use_reference_answer(
                state,
                rag_status=rag_result.status,
                fallback_reason=f"rag_status:{rag_result.status}",
                started_at=started_at,
            ):
                return state

        if rag_result is None or not rag_result.has_usable_hits:
            self._use_no_answer(
                state,
                status="no_answer",
                fallback_reason=f"rag_status:{rag_result.status if rag_result else 'missing'}",
                started_at=started_at,
            )
            return state

        if _lacks_substantive_request(state.user_query):
            self._use_no_answer(
                state,
                status="no_answer",
                fallback_reason="query_lacks_substantive_request",
                started_at=started_at,
            )
            return state

        if not self.settings.primary_llm.enabled:
            state.draft_answer = AnswerGenerator().compose_with_citations(rag_result)
            self._record(
                state,
                status="fallback",
                fallback_used=True,
                fallback_reason="primary_llm_disabled",
                started_at=started_at,
            )
            return state

        raw = await self.primary_llm_client.generate_json(
            PrimaryLLMRequest(
                prompt=self._prompt(state),
                schema_name="grounded_rag_answer",
                context=self._context(state, rag_result),
                system_prompt=(
                    "Return exactly one JSON object for grounded_rag_answer. "
                    "Answer in the user's language and use only facts contained in the supplied RAG evidence. "
                    "Cite factual statements with evidence indexes such as [1]. "
                    "Do not copy the retrieval result list or create a references section. "
                    "If the evidence supports any useful partial answer, set evidence_sufficient to true, "
                    "answer only the supported portion, and state its limits. Set it to false only when none "
                    "of the evidence supports a substantive answer or the animal species/topic is mismatched. "
                    "Do not diagnose, prescribe drugs, or provide drug dosages."
                ),
            )
        )
        raw = _normalize_grounded_payload(raw)
        try:
            payload = GroundedAnswerPayload.model_validate(raw)
        except ValidationError:
            self._use_no_answer(
                state,
                status="fallback",
                fallback_reason="schema_validation_failed",
                started_at=started_at,
            )
            return state

        if payload.fallback_required:
            self._use_no_answer(
                state,
                status="fallback",
                fallback_reason=payload.reason or "model_requested_fallback",
                started_at=started_at,
            )
            return state

        if not payload.evidence_sufficient and not _has_valid_evidence_citation(
            payload.answer_draft,
            evidence_count=len(rag_result.hits),
        ):
            if await self._use_reference_answer(
                state,
                rag_status="insufficient_evidence",
                fallback_reason=payload.reason or "insufficient_rag_evidence",
                started_at=started_at,
            ):
                return state
            self._use_no_answer(
                state,
                status="no_answer",
                fallback_reason=payload.reason or "insufficient_rag_evidence",
                started_at=started_at,
            )
            return state

        state.draft_answer = payload.answer_draft.strip()
        self._record(
            state,
            status="success",
            fallback_used=False,
            fallback_reason=None,
            started_at=started_at,
        )
        return state

    def _rag_result(self, state: MultiAgentState) -> RagSearchResult | None:
        value = state.tool_results.get(RAG_TOOL_NAME)
        if not isinstance(value, dict):
            return None
        return RagSearchResult.model_validate(value)

    def _context(self, state: MultiAgentState, result: RagSearchResult) -> dict[str, Any]:
        evidence = []
        for index, hit in enumerate(result.hits, start=1):
            evidence.append(
                {
                    "index": index,
                    "chunk_id": hit.chunk_id,
                    "source_uri": hit.source_uri,
                    "title": hit.document_title,
                    "score": hit.score,
                    "content": hit.content,
                }
            )
        return {
            "user_query": state.user_query,
            "normalized_query": state.normalized_query or state.user_query,
            "intent": state.intent,
            "rag_query": result.query,
            "evidence": evidence,
        }

    def _prompt(self, state: MultiAgentState) -> str:
        return (
            "Answer the user's question using only the supplied RAG evidence. "
            "Synthesize a concise, practical answer instead of listing retrieved files. "
            "A supported partial answer is preferable to refusing because the evidence is not exhaustive. "
            "Mark evidence insufficient only when it supports no useful answer to the actual species or topic.\n"
            f"User question: {(state.normalized_query or state.user_query).strip()}"
        )

    async def _use_reference_answer(
        self,
        state: MultiAgentState,
        *,
        rag_status: str,
        fallback_reason: str,
        started_at: float,
    ) -> bool:
        if not self.settings.primary_llm.enabled:
            return False

        try:
            raw = await self.primary_llm_client.generate_json(
                PrimaryLLMRequest(
                    prompt=(
                        "The knowledge base did not provide enough relevant evidence. "
                        "Give a short, cautious general-knowledge answer to the user's livestock question. "
                        "Use at most three brief points and answer in the user's language."
                    ),
                    schema_name="reference_only_answer",
                    context={
                        "user_query": state.user_query,
                        "normalized_query": state.normalized_query or state.user_query,
                        "intent": state.intent,
                        "rag_status": rag_status,
                    },
                    system_prompt=(
                        "Return exactly one JSON object with status=success and answer_draft. "
                        "This is an ungrounded, general-knowledge fallback because RAG evidence is insufficient. "
                        "Keep the answer brief and conservative. Do not invent citations, claim that the knowledge "
                        "base supports the answer, diagnose, prescribe drugs, or provide drug dosages."
                    ),
                )
            )
            payload = ReferenceOnlyAnswerPayload.model_validate(_normalize_reference_payload(raw))
        except Exception:
            return False

        if payload.fallback_required:
            return False

        answer = _strip_citation_markers(payload.answer_draft).strip()
        if not answer:
            return False

        state.draft_answer = _wrap_reference_answer(state.user_query, answer)
        state.evidence_status = "low_confidence"
        state.retrieved_contexts.clear()
        self._record(
            state,
            status="reference_only",
            fallback_used=True,
            fallback_reason=fallback_reason,
            reference_only=True,
            started_at=started_at,
        )
        return True

    def _use_no_answer(
        self,
        state: MultiAgentState,
        *,
        status: str,
        fallback_reason: str,
        started_at: float,
        answer_text: str = NO_ANSWER_TEXT,
    ) -> None:
        state.draft_answer = answer_text
        state.evidence_status = "low_confidence"
        state.retrieved_contexts.clear()
        self._record(
            state,
            status=status,
            fallback_used=status == "fallback",
            fallback_reason=fallback_reason,
            started_at=started_at,
        )

    def _discard_agentic_evidence(self, state: MultiAgentState) -> None:
        state.retrieved_contexts.clear()
        result = state.tool_results.get(RAG_TOOL_NAME)
        if isinstance(result, dict):
            result["status"] = "low_confidence"
            result["hits"] = []
            result["citations"] = []
            result["answer_text"] = None

    def _record(
        self,
        state: MultiAgentState,
        *,
        status: str,
        fallback_used: bool,
        fallback_reason: str | None,
        started_at: float,
        reference_only: bool = False,
    ) -> None:
        result = {
            "status": status,
            "schema_name": "reference_only_answer" if reference_only else "grounded_rag_answer",
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "reference_only": reference_only,
        }
        state.tool_results["grounded_answer_agent"] = result
        state.agent_trace.append(
            {
                "node": "grounded_answer_agent",
                "status": status,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "reference_only": reference_only,
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )


def _normalize_grounded_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    nested = payload.get("grounded_rag_answer")
    if isinstance(nested, dict):
        payload.update(nested)
    if not str(payload.get("answer_draft") or "").strip():
        for alias in ("grounded_rag_answer", "answer", "response", "message", "content", "text"):
            value = payload.get(alias)
            if isinstance(value, str) and value.strip():
                payload["answer_draft"] = value.strip()
                break
    if str(payload.get("answer_draft") or "").strip() and not payload.get("status"):
        payload["status"] = "success"
    return payload


def _normalize_reference_payload(raw: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw)
    nested = payload.get("reference_only_answer")
    if isinstance(nested, dict):
        payload.update(nested)
    if not str(payload.get("answer_draft") or "").strip():
        for alias in ("reference_only_answer", "answer", "response", "message", "content", "text"):
            value = payload.get(alias)
            if isinstance(value, str) and value.strip():
                payload["answer_draft"] = value.strip()
                break
    if str(payload.get("answer_draft") or "").strip() and payload.get("status") in {None, "", "ok", "completed"}:
        payload["status"] = "success"
    return payload


def _strip_citation_markers(answer: str) -> str:
    return re.sub(r"\s*\[(?:\d+|source[^\]]*)\]", "", answer, flags=re.IGNORECASE)


def _wrap_reference_answer(query: str, answer: str) -> str:
    if re.search(r"[\u3400-\u9fff]", query):
        return (
            "当前知识库没有检索到足够依据，因此无法给出确定回答。"
            "以下内容仅基于通用知识，供参考：\n\n"
            f"{answer}\n\n"
            "以上内容仅供参考；具体情况请咨询专业兽医或相关技术人员。"
        )
    return (
        "The knowledge base did not return enough evidence, so I cannot give a definitive answer. "
        "The following is a brief general-knowledge reference only:\n\n"
        f"{answer}\n\n"
        "For reference only; please consult a qualified veterinarian or livestock specialist "
        "for your specific situation."
    )


def _has_valid_evidence_citation(answer: str, *, evidence_count: int) -> bool:
    indexes = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    return any(1 <= index <= evidence_count for index in indexes)


def _lacks_substantive_request(query: str) -> bool:
    tokens = re.findall(r"[a-z]+", query.casefold())
    return bool(tokens) and all(token in _NON_SUBSTANTIVE_QUERY_TOKENS for token in tokens)
