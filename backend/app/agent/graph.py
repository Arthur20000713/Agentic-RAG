from __future__ import annotations

from uuid import uuid4

from backend.app.agent.disease_agent import DiseaseAgent
from backend.app.agent.rag_agent import RagAgent
from backend.app.agent.response_agent import ResponseAgent
from backend.app.agent.safety_agent import SafetyAgent
from backend.app.agent.state import MultiAgentState
from backend.app.agent.supervisor import SupervisorAgent
from backend.app.agent.verifier_agent import VerifierAgent
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.model.answer_generator import AnswerGenerator
from backend.app.schemas.rag_server import RagSearchResult


async def run_general_qa_graph(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_id: str | None = None,
) -> MultiAgentState:
    state = MultiAgentState(session_id=session_id or _new_session_id(), user_query=query)
    SupervisorAgent().route(state)
    await RagAgent(rag_client or FakeRagServerClient()).run(state)
    _compose_rag_draft(state)
    VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


async def run_disease_graph(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_id: str | None = None,
) -> MultiAgentState:
    state = MultiAgentState(session_id=session_id or _new_session_id(), user_query=query)
    SupervisorAgent().route(state)
    DiseaseAgent().run(state)
    if state.rag_query:
        disease_draft = state.draft_answer or ""
        await RagAgent(rag_client or FakeRagServerClient()).run(state)
        _compose_rag_draft(state, prefix=disease_draft)
        VerifierAgent().verify(state)
    SafetyAgent().check(state)
    ResponseAgent().render(state)
    return state


def _compose_rag_draft(state: MultiAgentState, *, prefix: str | None = None) -> None:
    rag_result = state.tool_results.get("livestock_rag_search")
    if isinstance(rag_result, dict):
        evidence_answer = AnswerGenerator().compose_with_citations(RagSearchResult.model_validate(rag_result))
        state.draft_answer = f"{prefix}\n\n{evidence_answer}" if prefix else evidence_answer


def _new_session_id() -> str:
    return f"s_{uuid4().hex}"
