from __future__ import annotations

import asyncio

from backend.app.agent.graph import run_disease_graph, run_general_qa_graph, run_measurement_graph
from backend.app.agent.rag_answer_policy import NO_ANSWER_POLICY_WARNING, NO_ANSWER_TEXT
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.model.intent_router import IntentRoutingResult
from backend.app.schemas.measurement import MeasurementInput
from backend.app.schemas.rag_server import RagCitation, RagSearchHit, RagSearchResult


class MissingCitationSourceRagClient(FakeRagServerClient):
    async def query(self, query: str, **kwargs) -> RagSearchResult:
        return RagSearchResult(
            query=query,
            status="success",
            hits=[
                RagSearchHit(
                    chunk_id="chunk_1",
                    document_title="guide",
                    content="context",
                    source_uri="rag://livestock/doc/chunk_1",
                    score=0.9,
                )
            ],
            citations=[RagCitation(title="guide", chunk_id="chunk_1")],
        )


class FakeReasoningClient:
    async def generate_json(self, request) -> dict:
        if request.schema_name == "disease_case_understanding":
            return {
                "status": "success",
                "schema_name": "disease_case_understanding",
                "case_summary": "Calf has diarrhea and reduced appetite.",
                "species": "cattle",
                "observed_signs": ["diarrhea", "reduced appetite"],
                "context_factors": ["fever mentioned"],
                "explicit_user_facts": {"group_context": "single animal"},
                "information_gaps": ["feces appearance"],
                "confidence": 0.9,
            }
        ref = request.context["evidence_gate"]["evidence_refs"][0]
        return {
            "status": "success",
            "schema_name": "disease_reasoning",
            "contributing_factors": [{"text": "Digestive disturbance may be relevant.", "evidence_refs": [ref]}],
            "uncertainties": ["Remote consultation cannot confirm a cause."],
            "follow_up_questions": ["What does the feces look like and has feed changed recently?"],
            "safe_actions": [{"text": "Monitor hydration and isolate if condition worsens.", "evidence_refs": [ref]}],
            "vet_triggers": [{"text": "Contact a vet if fever or depression appears.", "evidence_refs": [ref]}],
            "not_diagnosis_notice": "This is not a diagnosis.",
        }


class FakeDirectAnswerClient:
    async def generate_json(self, request) -> dict:
        return {
            "status": "success",
            "schema_name": request.schema_name,
            "answer_draft": "你好，我是由 LLM 生成草稿的畜牧业智能助手，可以结合知识库和工具帮助你。",
            "fallback_required": False,
        }


def test_general_qa_graph_runs_supervisor_rag_verifier_safety_response() -> None:
    state = asyncio.run(
        run_general_qa_graph(
            "How should cattle feeding be managed?",
            rag_client=FakeRagServerClient(),
            session_id="s_general_graph",
        )
    )

    assert state.session_id == "s_general_graph"
    assert state.intent == "general_qa"
    assert state.evidence_status == "success"
    assert state.draft_answer is not None
    assert state.final_answer is not None
    assert "参考依据" in state.final_answer
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.tool_results["response_agent"]["sources"][0]["source_uri"].startswith("rag://")
    assert [item["node"] for item in state.agent_trace] == [
        "supervisor",
        "rag_agent",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]


def test_general_qa_graph_records_query_normalizer_takeover_when_enabled() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["query_normalization"],
        },
        local_model={"enabled": True},
    )

    state = asyncio.run(
        run_general_qa_graph(
            "  How should cattle feeding be managed?  ",
            rag_client=FakeRagServerClient(),
            session_id="s_general_query_norm",
            settings=settings,
        )
    )

    assert state.normalized_query == "How should cattle feeding be managed?"
    assert state.tool_results["query_normalizer_router"]["route_decision"]["selected_model"] == "local_small"
    assert state.tool_results["query_normalizer_router"]["fallback_used"] is False
    assert [item["node"] for item in state.agent_trace][:2] == ["query_normalizer", "supervisor"]


def test_general_graph_uses_primary_llm_draft_for_assistant_intro_without_rag() -> None:
    settings = Settings(
        v3={"enabled": True},
        primary_llm={
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
        },
    )

    state = asyncio.run(
        run_general_qa_graph(
            "hello",
            rag_client=FakeRagServerClient(),
            session_id="s_intro_direct_llm",
            settings=settings,
            primary_llm_client=FakeDirectAnswerClient(),
        )
    )

    assert state.intent == "assistant_intro"
    assert "LLM 生成草稿" in state.final_answer
    assert "livestock_rag_search" not in state.tool_results
    assert state.tool_results["direct_answer_planner"]["fallback_used"] is False
    assert [item["node"] for item in state.agent_trace] == [
        "supervisor",
        "direct_answer_planner",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]


def test_general_qa_graph_keeps_low_confidence_no_answer_safe() -> None:
    state = asyncio.run(
        run_general_qa_graph(
            "low confidence cattle answer",
            rag_client=FakeRagServerClient(),
            session_id="s_low_graph",
        )
    )

    assert state.evidence_status == "low_confidence"
    assert state.final_answer is not None
    assert "没有检索到足够依据" in state.final_answer
    assert state.tool_results["response_agent"]["sources"] == []
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True


def test_general_qa_graph_policy_no_answer_keeps_rag_observable_without_contexts() -> None:
    state = asyncio.run(
        run_general_qa_graph(
            "What does this cattle corpus say about pet cat vaccination schedules?",
            rag_client=FakeRagServerClient(),
            session_id="s_policy_no_answer_graph",
        )
    )

    assert "livestock_rag_search" in state.tool_results
    assert state.tool_results["rag_answer_policy"]["warning"] == NO_ANSWER_POLICY_WARNING
    assert state.retrieved_contexts == []
    assert state.final_answer == NO_ANSWER_TEXT
    assert "[1]" not in state.final_answer
    assert state.tool_results["response_agent"]["sources"] == []
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True


def test_disease_graph_uses_rag_without_fixed_slot_follow_up() -> None:
    state = asyncio.run(
        run_disease_graph(
            "牛拉稀了怎么办？",
            rag_client=FakeRagServerClient(),
            session_id="s_disease_follow",
        )
    )

    assert state.intent == "disease_consultation"
    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "rag_ready"
    assert "livestock_rag_search" in state.tool_results
    assert "slot_extractor" not in state.tool_results
    assert "disease_slot_router" not in state.tool_results
    assert state.final_answer is not None
    assert "症状已经持续多久" not in state.final_answer
    assert "目前体温是多少" not in state.final_answer
    assert [item["node"] for item in state.agent_trace] == [
        "supervisor",
        "disease_agent",
        "rag_agent",
        "disease_evidence_gate",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]


def test_disease_graph_guardrails_model_route_misclassification(monkeypatch) -> None:
    async def fake_route_intent(*args, **kwargs):
        return IntentRoutingResult(
            intent="general_qa",
            confidence=0.99,
            reason="model misclassified disease case",
            should_use_rag=True,
            selected_model="local_small",
            route_mode="takeover",
            fallback_used=False,
        )

    monkeypatch.setattr("backend.app.agent.graph.route_intent_with_model", fake_route_intent)
    settings = Settings(
        v3={"enabled": True},
        model_router={
            "enabled": True,
            "shadow_mode": False,
            "allow_low_risk_takeover": True,
            "takeover_task_types": ["intent_routing"],
        },
        local_model={"enabled": True},
    )

    state = asyncio.run(
        run_disease_graph(
            "sick calf [species=cattle] [symptom=diarrhea]",
            rag_client=FakeRagServerClient(),
            session_id="s_disease_route_guard",
            settings=settings,
        )
    )

    assert state.intent == "disease_consultation"
    assert state.tool_results["intent_router_model"]["fallback_used"] is True
    assert state.tool_results["intent_router_model"]["fallback_reason"] == "disease_graph_guardrail"


def test_disease_graph_high_risk_uses_rag_verifier_safety_response() -> None:
    state = asyncio.run(
        run_disease_graph(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_id="s_disease_high",
        )
    )

    assert state.intent == "disease_consultation"
    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "rag_ready"
    assert state.evidence_status == "success"
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.final_answer is not None
    assert "初步风险等级" not in state.final_answer
    assert "参考依据" in state.final_answer
    assert "livestock_rag_search" in state.tool_results
    assert [item["node"] for item in state.agent_trace] == [
        "supervisor",
        "disease_agent",
        "rag_agent",
        "disease_evidence_gate",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]


def test_disease_graph_records_evidence_gate_rejection_for_unmapped_rag_refs() -> None:
    state = asyncio.run(
        run_disease_graph(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=MissingCitationSourceRagClient(),
            session_id="s_disease_gate",
        )
    )

    gate = state.tool_results["disease_evidence_gate"]

    assert gate["allowed"] is False
    assert gate["error_code"] == "RAG_VALID_EVIDENCE_MISSING"
    assert state.agent_trace[3]["node"] == "disease_evidence_gate"
    assert state.agent_trace[3]["status"] == "blocked"


def test_disease_graph_runs_reasoning_shadow_after_evidence_gate_when_enabled() -> None:
    settings = Settings(
        v3={"enabled": True},
        primary_llm={"enabled": True, "provider": "mock", "model": "mock", "base_url": "mock", "api_key_env": "X"},
        disease_llm={"enabled": True, "shadow_mode": True, "require_rag_evidence": True},
    )

    state = asyncio.run(
        run_disease_graph(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_id="s_disease_reasoning",
            settings=settings,
            primary_llm_client=FakeReasoningClient(),
        )
    )

    assert state.tool_results["disease_evidence_gate"]["allowed"] is True
    assert state.tool_results["disease_reasoning_shadow"]["status"] == "success"
    assert state.tool_results["disease_reasoning_shadow"]["reasoning"]["safe_actions"][0]["evidence_refs"]
    nodes = [item["node"] for item in state.agent_trace]
    gate_index = nodes.index("disease_evidence_gate")
    assert nodes[gate_index + 1] == "disease_reasoning_agent"


def test_disease_graph_reasoning_takeover_replaces_rule_risk_draft_when_enabled() -> None:
    settings = Settings(
        v3={"enabled": True},
        primary_llm={"enabled": True, "provider": "mock", "model": "mock", "base_url": "mock", "api_key_env": "X"},
        disease_llm={"enabled": True, "shadow_mode": False, "require_rag_evidence": True},
    )

    state = asyncio.run(
        run_disease_graph(
            "犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病",
            rag_client=FakeRagServerClient(),
            session_id="s_disease_takeover",
            settings=settings,
            primary_llm_client=FakeReasoningClient(),
        )
    )

    assert state.tool_results["disease_reasoning"]["status"] == "success"
    assert state.final_answer is not None
    assert "Digestive disturbance may be relevant." in state.final_answer
    assert "Monitor hydration" in state.final_answer
    assert "feces look like" in state.final_answer
    assert "rag://" in state.final_answer
    assert "初步风险等级" not in state.final_answer
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True


def test_disease_graph_does_not_use_router_slot_extraction() -> None:
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": False, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )

    state = asyncio.run(
        run_disease_graph(
            "犊牛腹泻了怎么办？",
            rag_client=FakeRagServerClient(),
            session_id="s_disease_no_slot_router",
            settings=settings,
        )
    )

    assert state.disease_assessment is not None
    assert state.disease_assessment["status"] == "rag_ready"
    assert "livestock_rag_search" in state.tool_results
    assert "disease_slot_router" not in state.tool_results
    assert "slot_extractor" not in state.tool_results
    assert state.final_answer is not None


def test_measurement_graph_runs_without_rag_and_preserves_evidence() -> None:
    measurement = MeasurementInput(
        animal_id="yak_032",
        current={"chest_girth_cm": 158.4, "weight_kg": 246.5},
        history=[
            {
                "measure_date": "2026-04-01",
                "chest_girth_cm": 157.0,
                "weight_kg": 242.0,
            }
        ],
        confidence=0.82,
    )

    state = asyncio.run(run_measurement_graph(measurement, session_id="s_measure_graph"))

    assert state.intent == "measurement_analysis"
    assert state.measurement_report is not None
    assert "chest_girth_cm" in state.measurement_report["abnormal_items"]
    assert "livestock_rag_search" not in state.tool_results
    assert state.rag_query is None
    assert state.verification_result is not None
    assert state.verification_result["passed"] is True
    assert state.safety_result is not None
    assert state.safety_result["passed"] is True
    assert state.final_answer is not None
    assert "增长 1.4 cm" in state.final_answer
    assert [item["node"] for item in state.agent_trace] == [
        "supervisor",
        "measurement_agent",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]


def test_measurement_graph_without_history_still_returns_report() -> None:
    measurement = MeasurementInput(
        animal_id="yak_001",
        current={"body_height_cm": 114.2, "weight_kg": 246.5},
        confidence=0.82,
    )

    state = asyncio.run(run_measurement_graph(measurement, session_id="s_measure_none"))

    assert state.intent == "measurement_analysis"
    assert state.measurement_report is not None
    assert state.measurement_report["abnormal_items"] == []
    assert state.final_answer is not None
    assert "无历史记录" in state.final_answer


def test_measurement_graph_records_shadow_route_without_changing_answer() -> None:
    measurement = MeasurementInput(
        animal_id="yak_032",
        current={"chest_girth_cm": 158.4, "weight_kg": 246.5},
        history=[
            {
                "measure_date": "2026-04-01",
                "chest_girth_cm": 157.0,
                "weight_kg": 242.0,
            }
        ],
        confidence=0.82,
    )
    settings = Settings(
        v3={"enabled": True},
        model_router={"enabled": True, "shadow_mode": True, "allow_low_risk_takeover": True},
        local_model={"enabled": True},
    )

    baseline = asyncio.run(run_measurement_graph(measurement, session_id="s_measure_shadow_base"))
    shadow = asyncio.run(run_measurement_graph(measurement, session_id="s_measure_shadow", settings=settings))

    assert shadow.final_answer == baseline.final_answer
    assert shadow.measurement_report == baseline.measurement_report
    assert shadow.tool_results["model_router_shadow"]["route_decision"]["route_mode"] == "shadow"
    assert shadow.tool_results["model_router_shadow"]["route_decision"]["selected_model"] == "primary"
    assert shadow.tool_results["model_router_shadow"]["route_decision"]["shadow_model"] == "local_small"
    assert [item["node"] for item in shadow.agent_trace] == [
        "supervisor",
        "model_router_shadow",
        "measurement_agent",
        "verifier_agent",
        "safety_agent",
        "response_agent",
    ]
