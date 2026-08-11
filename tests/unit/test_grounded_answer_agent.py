from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.grounded_answer_agent import GroundedAnswerAgent
from backend.app.agent.rag_answer_policy import NO_ANSWER_TEXT
from backend.app.agent.response_agent import ResponseAgent
from backend.app.agent.state import MultiAgentState
from backend.app.agent.verifier_agent import VerifierAgent
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMRequest
from backend.app.schemas.agent import RetrievedContext
from backend.app.schemas.rag_server import RagCitation, RagSearchHit, RagSearchResult
from backend.app.services.chat_service import state_to_chat_data


class FakePrimaryLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[PrimaryLLMRequest] = []

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.payload


class SequentialFakePrimaryLLM:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.requests: list[PrimaryLLMRequest] = []

    async def generate_json(self, request: PrimaryLLMRequest) -> dict[str, Any]:
        self.requests.append(request)
        return self.payloads[len(self.requests) - 1]


def _settings() -> Settings:
    return Settings(
        primary_llm={"enabled": True, "provider": "mock", "model": "mock", "base_url": "mock"},
    )


def _state() -> MultiAgentState:
    result = RagSearchResult(
        query="How should calves be fed after weaning?",
        status="success",
        answer_text="## Query Results\nretrieval dump",
        hits=[
            RagSearchHit(
                chunk_id="chunk_1",
                document_title="Calf feeding guide",
                content="Keep the feeding schedule stable and provide clean water.",
                source_uri="rag://livestock/doc/chunk_1",
                score=0.88,
            )
        ],
        citations=[
            RagCitation(
                source_id="doc",
                source_uri="rag://livestock/doc/chunk_1",
                title="Calf feeding guide",
                chunk_id="chunk_1",
            )
        ],
    )
    state = MultiAgentState(
        session_id="s1",
        user_query=result.query,
        normalized_query=result.query,
        intent="general_qa",
        evidence_status="success",
        retrieved_contexts=[
            RetrievedContext(
                chunk_id="chunk_1",
                title="Calf feeding guide",
                content="Keep the feeding schedule stable and provide clean water.",
                score=0.88,
            )
        ],
    )
    state.tool_results["livestock_rag_search"] = result.model_dump()
    return state


def _empty_state() -> MultiAgentState:
    result = RagSearchResult(
        query="How should a goat be sheltered during a cold rain?",
        status="empty",
    )
    state = MultiAgentState(
        session_id="s_empty",
        user_query=result.query,
        normalized_query=result.query,
        intent="general_qa",
        evidence_status="empty",
    )
    state.tool_results["livestock_rag_search"] = result.model_dump()
    return state


def test_grounded_answer_agent_synthesizes_answer_from_rag_context() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "grounded_rag_answer",
            "answer_draft": "Keep the feeding schedule stable and provide clean water [1].",
            "evidence_sufficient": True,
            "fallback_required": False,
        }
    )
    state = _state()

    asyncio.run(GroundedAnswerAgent(_settings(), primary_llm_client=llm).run(state))

    assert state.draft_answer == "Keep the feeding schedule stable and provide clean water [1]."
    assert llm.requests[0].schema_name == "grounded_rag_answer"
    assert llm.requests[0].context["evidence"][0]["chunk_id"] == "chunk_1"
    assert llm.requests[0].context["evidence"][0]["content"].startswith("Keep the feeding")
    assert state.tool_results["grounded_answer_agent"]["status"] == "success"
    assert state.agent_trace[-1]["node"] == "grounded_answer_agent"


def test_grounded_answer_agent_uses_reference_only_answer_when_model_rejects_evidence() -> None:
    llm = SequentialFakePrimaryLLM(
        [
            {
                "status": "success",
                "schema_name": "grounded_rag_answer",
                "answer_draft": "The retrieved cattle documents do not answer this poultry question.",
                "evidence_sufficient": False,
                "fallback_required": False,
                "reason": "species_mismatch",
            },
            {
                "status": "success",
                "answer_draft": "Keep poultry housing dry, ventilated, and protected from drafts.",
            },
        ]
    )
    state = _state()

    asyncio.run(GroundedAnswerAgent(_settings(), primary_llm_client=llm).run(state))

    assert len(llm.requests) == 2
    assert llm.requests[1].schema_name == "reference_only_answer"
    assert "did not return enough evidence" in state.draft_answer
    assert "Keep poultry housing dry" in state.draft_answer
    assert state.evidence_status == "low_confidence"
    assert state.retrieved_contexts == []
    assert state.tool_results["grounded_answer_agent"]["status"] == "reference_only"
    assert state.tool_results["grounded_answer_agent"]["fallback_reason"] == "species_mismatch"
    ResponseAgent().render(state)
    assert state_to_chat_data(state, settings=_settings())["sources"] == []


def test_grounded_answer_agent_accepts_schema_named_answer_alias() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "grounded_rag_answer",
            "grounded_rag_answer": "Use a stable weaning transition and provide clean water [1].",
            "evidence_sufficient": True,
            "fallback_required": False,
        }
    )
    state = _state()

    asyncio.run(GroundedAnswerAgent(_settings(), primary_llm_client=llm).run(state))

    assert state.draft_answer == "Use a stable weaning transition and provide clean water [1]."
    assert state.tool_results["grounded_answer_agent"]["status"] == "success"


def test_grounded_answer_agent_keeps_supported_partial_answer() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "schema_name": "grounded_rag_answer",
            "grounded_rag_answer": "The evidence supports a stable weaning transition [1], but not a full ration plan.",
            "evidence_sufficient": False,
            "fallback_required": False,
        }
    )
    state = _state()

    asyncio.run(GroundedAnswerAgent(_settings(), primary_llm_client=llm).run(state))

    assert "stable weaning transition [1]" in state.draft_answer
    assert state.evidence_status == "success"
    assert state.tool_results["grounded_answer_agent"]["status"] == "success"


def test_grounded_answer_agent_does_not_expose_retrieval_dump_on_model_failure() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "error",
            "schema_name": "grounded_rag_answer",
            "fallback_required": True,
            "reason": "upstream unavailable",
        }
    )
    state = _state()

    asyncio.run(GroundedAnswerAgent(_settings(), primary_llm_client=llm).run(state))

    assert state.draft_answer == NO_ANSWER_TEXT
    assert "Query Results" not in state.draft_answer
    assert state.tool_results["grounded_answer_agent"]["status"] == "fallback"


def test_grounded_answer_agent_accepts_nested_payload_without_explicit_status() -> None:
    llm = FakePrimaryLLM(
        {
            "grounded_rag_answer": {
                "answer_draft": "Provide clean water during the weaning transition [1].",
                "evidence_sufficient": True,
            }
        }
    )
    state = _state()

    asyncio.run(GroundedAnswerAgent(_settings(), primary_llm_client=llm).run(state))

    assert state.draft_answer == "Provide clean water during the weaning transition [1]."
    assert state.evidence_status == "success"


def test_grounded_answer_agent_uses_reference_only_llm_answer_when_rag_is_empty() -> None:
    llm = FakePrimaryLLM(
        {
            "status": "success",
            "answer_draft": "- Keep the animals dry and protected from wind.\n- Monitor feeding and behavior closely.",
        }
    )
    state = _empty_state()

    asyncio.run(GroundedAnswerAgent(_settings(), primary_llm_client=llm).run(state))
    VerifierAgent().verify(state)
    ResponseAgent().render(state)

    assert llm.requests[0].schema_name == "reference_only_answer"
    assert "did not return enough evidence" in state.draft_answer
    assert "reference only" in state.draft_answer.lower()
    assert "qualified veterinarian or livestock specialist" in state.draft_answer
    assert "Keep the animals dry" in state.draft_answer
    assert state.evidence_status == "low_confidence"
    assert state.retrieved_contexts == []
    assert state.tool_results["grounded_answer_agent"]["status"] == "reference_only"
    assert state.tool_results["grounded_answer_agent"]["schema_name"] == "reference_only_answer"
    assert state.tool_results["grounded_answer_agent"]["reference_only"] is True
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state_to_chat_data(state, settings=_settings())["sources"] == []
