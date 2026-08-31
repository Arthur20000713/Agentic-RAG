from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.langgraph_workflow import AgentGraphRuntime, build_chat_graph
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.schemas.api import ChatRequest
from backend.app.schemas.rag_server import RagSearchResult
from backend.app.services.chat_service import ChatService, build_agent_runtime_debug_payload


class FakePrimaryLLMClient:
    async def generate_json(self, request: Any) -> dict[str, Any]:
        if request.schema_name == "disease_case_understanding":
            return {
                "status": "success",
                "schema_name": request.schema_name,
                "case_summary": "A calf has diarrhea and reduced appetite.",
                "species": "cattle",
                "observed_signs": ["diarrhea", "reduced appetite"],
                "context_factors": ["symptoms have lasted two days"],
                "confidence": 0.9,
            }
        if request.schema_name == "grounded_rag_answer":
            return {
                "status": "success",
                "schema_name": request.schema_name,
                "answer_draft": "Use the retrieved livestock guidance to monitor feeding and hydration [1].",
                "evidence_sufficient": True,
                "fallback_required": False,
            }
        if request.schema_name == "reference_only_answer":
            return {
                "status": "success",
                "schema_name": request.schema_name,
                "answer_draft": "Monitor feed intake, hydration, housing, and behavior.",
            }
        return {
            "status": "success",
            "schema_name": request.schema_name,
            "answer_draft": "Here is a short ordinary-chat reply from the LLM.",
            "fallback_required": False,
        }


class CountingRagClient(FakeRagServerClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0
        self.queries: list[str] = []
        self.top_ks: list[int | None] = []

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        self.queries.append(query)
        self.top_ks.append(kwargs.get("top_k"))
        return await super().query(query, **kwargs)


class AlwaysErrorRagClient(FakeRagServerClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0

    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        return RagSearchResult(
            query=query,
            status="error",
            error_code="RAG_UNAVAILABLE",
            error_message="controlled test failure",
        )


class TransientErrorRagClient(CountingRagClient):
    async def query(self, query: str, **kwargs: Any) -> RagSearchResult:
        self.query_count += 1
        if self.query_count == 1:
            return RagSearchResult(
                query=query,
                status="error",
                error_code="RAG_TRANSIENT",
                error_message="controlled transient failure",
            )
        return await FakeRagServerClient.query(self, query, **kwargs)


def _settings() -> Settings:
    return Settings(
        primary_llm={
            "enabled": True,
            "provider": "mock",
            "model": "mock",
            "base_url": "mock",
        },
        disease_llm={"enabled": True, "shadow_mode": False},
    )


def _invoke_state(
    state: MultiAgentState,
    *,
    rag_client: FakeRagServerClient,
    forced_intent: str | None = None,
) -> MultiAgentState:
    graph = build_chat_graph()
    runtime = AgentGraphRuntime(
        settings=_settings(),
        rag_client=rag_client,
        primary_llm_client=FakePrimaryLLMClient(),
        forced_intent=forced_intent,
    )

    async def invoke() -> Any:
        return await asyncio.wait_for(
            graph.ainvoke(
                state,
                context=runtime,
            ),
            timeout=3,
        )

    result = asyncio.run(invoke())
    return result if isinstance(result, MultiAgentState) else MultiAgentState.model_validate(result)


def _run_chat(query: str, *, rag_client: FakeRagServerClient) -> MultiAgentState:
    return _invoke_state(
        MultiAgentState(session_id="s_langgraph_test", user_query=query),
        rag_client=rag_client,
    )


def test_ordinary_chat_uses_direct_llm_branch_without_rag() -> None:
    rag_client = CountingRagClient()

    state = _run_chat("Tell me a short joke.", rag_client=rag_client)

    assert state.intent == "out_of_scope"
    assert state.final_answer is not None
    assert "ordinary-chat reply" in state.final_answer
    assert rag_client.query_count == 0
    assert "livestock_rag_search" not in state.tool_results
    assert state.tool_plan == []


def test_livestock_question_uses_planned_rag_tool_then_grounded_reasoning() -> None:
    rag_client = CountingRagClient()

    state = _run_chat("How should cattle feeding be managed during hot weather?", rag_client=rag_client)

    assert state.intent == "general_qa"
    assert rag_client.query_count == 1
    assert state.tool_attempt == 1
    assert state.tool_plan[0]["tool"] == "query_knowledge_hub"
    assert "livestock_rag_search" in state.tool_results
    assert state.retrieved_contexts
    assert state.evidence_status == "success"
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.final_answer is not None
    assert "retrieved livestock guidance" in state.final_answer
    assert "## Query Results" not in state.final_answer


def test_disease_branch_uses_generic_verifier_and_safety_without_disease_gate() -> None:
    rag_client = CountingRagClient()

    state = _run_chat("A calf has diarrhea and reduced appetite for two days.", rag_client=rag_client)

    assert state.intent == "disease_consultation"
    assert rag_client.query_count == 1
    assert "livestock_rag_search" in state.tool_results
    assert "verifier_agent" in state.tool_results
    assert "disease_evidence_gate" not in state.tool_results
    assert "disease_reasoning" not in state.tool_results
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.final_answer is not None


def test_rag_error_retries_once_then_finishes_with_safe_fallback() -> None:
    rag_client = AlwaysErrorRagClient()

    state = _run_chat("How should cattle feeding error recovery be managed?", rag_client=rag_client)

    assert rag_client.query_count == 2
    assert state.tool_attempt == 2
    assert state.evidence_status in {"error", "low_confidence"}
    assert state.retrieved_contexts == []
    assert state.final_answer is not None
    assert state.tool_results["response_agent"]["sources"] == []
    assert len([item for item in state.agent_trace if item.get("node") == "rag_agent"]) == 2


def test_transient_rag_error_recovers_without_leaking_first_attempt_error() -> None:
    rag_client = TransientErrorRagClient()

    state = _run_chat("How should cattle feeding be managed?", rag_client=rag_client)

    assert rag_client.query_count == 2
    assert state.tool_attempt == 2
    assert state.evidence_status == "success"
    assert state.retrieved_contexts
    assert not [error for error in state.errors if error.tool_name == "rag_agent"]
    retry_history = state.tool_results["rag_retry_history"]
    assert len(retry_history) == 1
    assert retry_history[0]["error_code"] == "RAG_TRANSIENT"


def test_graph_rejects_preinjected_non_allowlisted_tool_without_calling_rag() -> None:
    rag_client = CountingRagClient()
    initial = MultiAgentState(
        session_id="s_invalid_tool_plan",
        user_query="How should cattle feeding be managed?",
        tool_plan=[{"tool": "shell_command", "arguments": {"command": "whoami"}}],
    )

    state = _invoke_state(initial, rag_client=rag_client, forced_intent="general_qa")

    assert rag_client.query_count == 0
    assert state.tool_attempt == 0
    assert state.evidence_status in {"error", "low_confidence"}
    assert state.tool_results["tool_plan_validation"] == {
        "valid": False,
        "error_code": "PLANNER_TOOL_NOT_ALLOWED",
    }
    assert any(
        error.tool_name == "planner" and error.error_code == "PLANNER_TOOL_NOT_ALLOWED"
        for error in state.errors
    )
    assert state.final_answer is not None
    assert state.tool_results["response_agent"]["sources"] == []


def test_legacy_tool_plan_cannot_override_trusted_query_or_bounds() -> None:
    rag_client = CountingRagClient()
    initial = MultiAgentState(
        session_id="s_planned_tool_arguments",
        user_query="original livestock question",
        tool_plan=[
            {
                "tool": "query_knowledge_hub",
                "arguments": {"query": "planner rewritten cattle feeding query", "top_k": 2},
            }
        ],
    )

    state = _invoke_state(initial, rag_client=rag_client, forced_intent="general_qa")

    assert rag_client.query_count == 1
    assert rag_client.queries == ["original livestock question"]
    assert rag_client.top_ks == [4]
    assert state.rag_query == "original livestock question"


def test_chat_service_delegates_every_query_to_the_unified_graph(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_run_chat_graph(query: str, **kwargs: Any) -> MultiAgentState:
        calls.append(query)
        return MultiAgentState(
            session_id=str(kwargs.get("session_id") or "s_unified"),
            user_query=query,
            intent="out_of_scope",
            final_answer="unified graph reply",
        )

    monkeypatch.setattr("backend.app.services.chat_service.run_chat_graph", fake_run_chat_graph)
    service = ChatService(FakeRagServerClient(), settings=_settings())


    queries = [
        "Tell me a short joke.",
        "How should cattle feeding be managed?",
        "A calf has diarrhea.",
    ]

    for index, query in enumerate(queries):
        result = asyncio.run(
            service.ask(ChatRequest(query=query, session_id=f"s_unified_{index}"))
        )
        assert result.final_answer == "unified graph reply"

    assert calls == queries


def test_langgraph_state_is_identified_in_debug_payload() -> None:
    state = MultiAgentState(
        session_id="s_langgraph_debug",
        user_query="hello",
        intent="assistant_intro",
        final_answer="hello",
    )

    payload = build_agent_runtime_debug_payload(_settings(), state=state)

    assert payload["orchestration_engine"] == "langgraph"
