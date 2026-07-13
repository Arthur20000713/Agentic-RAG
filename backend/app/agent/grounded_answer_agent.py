from __future__ import annotations

import re
import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.rag_answer_policy import NO_ANSWER_TEXT
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.answer_generator import AnswerGenerator
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest
from backend.app.schemas.rag_server import RagSearchResult


RAG_TOOL_NAME = "livestock_rag_search"


class GroundedAnswerPayload(BaseModel):
    status: Literal["success"]
    schema_name: str = "grounded_rag_answer"
    answer_draft: str = Field(min_length=1)
    evidence_sufficient: bool = True
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

        if rag_result is None or not rag_result.has_usable_hits:
            self._use_no_answer(
                state,
                status="no_answer",
                fallback_reason=f"rag_status:{rag_result.status if rag_result else 'missing'}",
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

    def _use_no_answer(
        self,
        state: MultiAgentState,
        *,
        status: str,
        fallback_reason: str,
        started_at: float,
    ) -> None:
        state.draft_answer = NO_ANSWER_TEXT
        state.evidence_status = "low_confidence"
        state.retrieved_contexts.clear()
        self._record(
            state,
            status=status,
            fallback_used=status == "fallback",
            fallback_reason=fallback_reason,
            started_at=started_at,
        )

    def _record(
        self,
        state: MultiAgentState,
        *,
        status: str,
        fallback_used: bool,
        fallback_reason: str | None,
        started_at: float,
    ) -> None:
        result = {
            "status": status,
            "schema_name": "grounded_rag_answer",
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
        }
        state.tool_results["grounded_answer_agent"] = result
        state.agent_trace.append(
            {
                "node": "grounded_answer_agent",
                "status": status,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
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


def _has_valid_evidence_citation(answer: str, *, evidence_count: int) -> bool:
    indexes = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    return any(1 <= index <= evidence_count for index in indexes)
