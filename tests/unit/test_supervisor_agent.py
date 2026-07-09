from __future__ import annotations

from backend.app.agent.state import MultiAgentState
from backend.app.model.intent_router import IntentRoutingResult
from backend.app.agent.supervisor import SupervisorAgent


def test_supervisor_routes_general_qa_and_appends_trace() -> None:
    state = MultiAgentState(session_id="s1", user_query="How should calf feeding be managed?")

    routed = SupervisorAgent().route(state)

    assert routed is state
    assert state.intent == "general_qa"
    assert state.active_agent == "rag_agent"
    assert state.route_reason == "livestock domain keyword matched"
    assert state.tool_results["supervisor"]["intent"] == "general_qa"
    assert state.agent_trace[-1]["node"] == "supervisor"
    assert state.agent_trace[-1]["status"] == "success"
    assert state.agent_trace[-1]["active_agent"] == "rag_agent"


def test_supervisor_routes_english_disease_measurement_and_out_of_scope() -> None:
    supervisor = SupervisorAgent()

    disease = supervisor.route(MultiAgentState(session_id="s1", user_query="Calf diarrhea and fever"))
    measurement = supervisor.route(MultiAgentState(session_id="s2", user_query="Analyze cattle chest girth"))
    out_of_scope = supervisor.route(MultiAgentState(session_id="s3", user_query="Write code for stock trading"))

    assert disease.intent == "disease_consultation"
    assert disease.active_agent == "disease_agent"
    assert measurement.intent == "measurement_analysis"
    assert measurement.active_agent == "measurement_agent"
    assert out_of_scope.intent == "out_of_scope"
    assert out_of_scope.active_agent == "response_agent"


def test_supervisor_preserves_existing_normalized_query() -> None:
    state = MultiAgentState(
        session_id="s1",
        user_query="Calf feeding",
        normalized_query="normalized calf feeding",
    )

    SupervisorAgent().route(state)

    assert state.normalized_query == "normalized calf feeding"


def test_supervisor_can_use_model_route_override() -> None:
    state = MultiAgentState(session_id="s1", user_query="hello")
    route = IntentRoutingResult(
        intent="assistant_intro",
        confidence=0.92,
        reason="greeting",
        should_use_rag=False,
        selected_model="local_small",
        route_mode="takeover",
        fallback_used=False,
    )

    SupervisorAgent().route(state, route_override=route)

    assert state.intent == "assistant_intro"
    assert state.active_agent == "response_agent"
    assert state.tool_results["supervisor"]["route_source"] == "model"
    assert state.tool_results["intent_router_model"]["selected_model"] == "local_small"
    assert state.tool_results["intent_router_model"]["should_use_rag"] is False
