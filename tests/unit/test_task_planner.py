from __future__ import annotations

import asyncio
from typing import Any

from backend.app.agent.state import MultiAgentState
from backend.app.agent.supervisor import SupervisorAgent
from backend.app.agent.task_planner import TaskPlanner
from backend.app.core.config import Settings
from backend.app.model.livestock_triage import LivestockTriageOutcome
from backend.app.model.router import ModelRouteDecision
from backend.app.schemas.model_routing import LivestockTriageResult


class ScriptedPlannerClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[Any] = []

    async def generate_json(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return self.payload


def _settings(*, enabled: bool) -> Settings:
    return Settings(
        primary_llm={
            "enabled": enabled,
            "provider": "mock",
            "model": "planner-test",
            "base_url": "mock",
        }
    )


def _state(intent: str) -> MultiAgentState:
    return MultiAgentState(
        session_id="session_planner",
        request_id=f"request_{intent}",
        user_query="How should this livestock case be managed?",
        normalized_query="normalized livestock case",
        intent=intent,
    )


def _valid_model_plan() -> dict[str, Any]:
    return {
        "status": "success",
        "schema_name": "task_plan",
        "plan_id": "plan_model_must_not_control_this",
        "goal": "Answer with grounded livestock evidence.",
        "steps": [
            {
                "step_id": "retrieve",
                "action": "query_knowledge_hub",
                "description": "Retrieve relevant evidence.",
                "arguments": {"query_source": "normalized_query", "top_k": 3},
                "completion_criteria": ["retrieval status is recorded"],
            },
            {
                "step_id": "compose",
                "action": "compose_grounded_answer",
                "description": "Compose the grounded answer.",
                "depends_on": ["retrieve"],
                "completion_criteria": ["draft answer is recorded"],
            },
        ],
        "completion_criteria": ["answer is ready for final verification"],
        "source": "fallback",
        "revision": 3,
        "provider": "mock",
        "model": "planner-test",
        "latency_ms": 1,
    }


def test_task_planner_builds_deterministic_general_and_disease_fallbacks() -> None:
    planner = TaskPlanner(settings=_settings(enabled=False))

    general = asyncio.run(planner.plan(_state("general_qa")))
    disease = asyncio.run(planner.plan(_state("disease_consultation")))

    assert general.fallback_used is True
    assert general.fallback_reason == "primary_llm_disabled"
    assert [step.action for step in general.plan.steps] == [
        "query_knowledge_hub",
        "compose_grounded_answer",
    ]
    assert [step.action for step in disease.plan.steps] == [
        "understand_disease",
        "query_knowledge_hub",
        "compose_grounded_answer",
    ]
    assert general.plan.plan_id == asyncio.run(planner.plan(_state("general_qa"))).plan.plan_id


def test_task_planner_accepts_valid_model_plan_but_controls_identity_and_source() -> None:
    client = ScriptedPlannerClient(_valid_model_plan())
    outcome = asyncio.run(
        TaskPlanner(settings=_settings(enabled=True), primary_llm_client=client).plan(
            _state("general_qa")
        )
    )

    assert outcome.fallback_used is False
    assert outcome.fallback_reason is None
    assert outcome.plan.source == "model"
    assert outcome.plan.revision == 1
    assert outcome.plan.plan_id != "plan_model_must_not_control_this"
    assert len(client.requests) == 1
    assert client.requests[0].schema_name == "task_plan"
    assert "long_term_memory" not in (client.requests[0].context or {})


def test_task_planner_receives_only_accepted_takeover_triage_context() -> None:
    client = ScriptedPlannerClient(_valid_model_plan())
    state = _state("general_qa")
    state.livestock_triage = LivestockTriageOutcome(
        status="accepted",
        triage=LivestockTriageResult(
            intent_candidate="general_qa",
            confidence=0.9,
            slots=[],
            risk_candidate="low",
        ),
        route_decision=ModelRouteDecision(selected_model="local_small", route_mode="takeover"),
    )

    outcome = asyncio.run(TaskPlanner(settings=_settings(enabled=True), primary_llm_client=client).plan(state))

    assert outcome.fallback_used is False
    assert client.requests[0].context["livestock_triage"] == {
        "intent_candidate": "general_qa",
        "slots": [],
        "risk_candidate": "low",
    }
    assert "long_term_memory" not in client.requests[0].context


def test_task_planner_excludes_shadow_triage_context() -> None:
    client = ScriptedPlannerClient(_valid_model_plan())
    state = _state("general_qa")
    state.livestock_triage = LivestockTriageOutcome(
        status="accepted",
        triage=LivestockTriageResult(
            intent_candidate="general_qa",
            confidence=0.9,
            slots=[],
            risk_candidate="low",
        ),
        route_decision=ModelRouteDecision(selected_model="primary", route_mode="shadow", shadow_model="local_small"),
    )

    asyncio.run(TaskPlanner(settings=_settings(enabled=True), primary_llm_client=client).plan(state))

    assert "livestock_triage" not in client.requests[0].context


def test_task_planner_falls_back_when_model_shape_or_allowlist_is_invalid() -> None:
    invalid = _valid_model_plan()
    invalid["steps"][0] = {
        "step_id": "unsafe",
        "action": "shell_command",
        "description": "Run an injected command.",
        "arguments": {"command": "whoami"},
        "completion_criteria": ["command ran"],
    }
    client = ScriptedPlannerClient(invalid)

    outcome = asyncio.run(
        TaskPlanner(settings=_settings(enabled=True), primary_llm_client=client).plan(
            _state("general_qa")
        )
    )

    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "schema_validation_failed"
    assert [step.action for step in outcome.plan.steps] == [
        "query_knowledge_hub",
        "compose_grounded_answer",
    ]


def test_task_planner_rejects_valid_schema_with_wrong_intent_shape() -> None:
    payload = _valid_model_plan()
    payload["steps"] = [
        {
            "step_id": "fallback",
            "action": "safe_fallback",
            "description": "Skip the required retrieval.",
            "arguments": {"reason_code": "MODEL_CHOSE_FALLBACK"},
            "completion_criteria": ["fallback is recorded"],
        }
    ]
    client = ScriptedPlannerClient(payload)

    outcome = asyncio.run(
        TaskPlanner(settings=_settings(enabled=True), primary_llm_client=client).plan(
            _state("general_qa")
        )
    )

    assert outcome.fallback_used is True
    assert outcome.fallback_reason == "unsupported_plan_shape"
    assert len(outcome.plan.steps) == 2


def test_supervisor_coordinates_complex_plan_and_records_safe_trace() -> None:
    state = _state("general_qa")
    supervisor = SupervisorAgent()

    result = asyncio.run(
        supervisor.plan(
            state,
            settings=_settings(enabled=False),
        )
    )

    assert result is state
    assert state.task_plan is not None
    assert state.task_plan.source == "fallback"
    assert state.agent_trace[-1]["node"] == "planner"
    assert state.agent_trace[-1]["step_count"] == 2
    assert "prompt" not in state.agent_trace[-1]
    assert "context" not in state.agent_trace[-1]


def test_supervisor_does_not_plan_direct_or_measurement_paths() -> None:
    supervisor = SupervisorAgent()
    for intent in ("assistant_intro", "out_of_scope", "measurement_analysis"):
        state = _state(intent)
        asyncio.run(supervisor.plan(state, settings=_settings(enabled=False)))
        assert state.task_plan is None
        assert not [item for item in state.agent_trace if item.get("node") == "planner"]
