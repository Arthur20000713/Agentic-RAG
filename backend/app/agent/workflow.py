from __future__ import annotations

from uuid import uuid4

from backend.app.agent.extractor import SlotExtractor, build_follow_up_questions
from backend.app.agent.rag_answer_policy import (
    NO_ANSWER_TEXT,
    RagAnswerPolicyDecision,
    SAFETY_REFUSAL_TEXT,
    classify_rag_answer_policy,
)
from backend.app.agent.safety import FinalSafetyGuard
from backend.app.agent.safety_precheck import SafetyPrecheck
from backend.app.agent.verifier import VerifierLite
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.model.answer_generator import AnswerGenerator
from backend.app.rules.disease_risk import DiseaseRiskEvaluator
from backend.app.schemas.agent import AgentState, AgentToolError, RetrievedContext
from backend.app.schemas.measurement import MeasurementInput
from backend.app.schemas.rag_server import RagSearchResult
from backend.app.services.measurement_service import BodyMeasurementAnalyzer


async def run_general_qa(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
) -> AgentState:
    rag_client = rag_client or FakeRagServerClient()
    state = AgentState(session_id=session_id or _new_session_id(), user_query=query, intent="general_qa", intent_confidence=0.8)
    policy = classify_rag_answer_policy(query)

    rag_result = await rag_client.query(query, top_k=4, request_id=request_id)
    state.tool_results["livestock_rag_search"] = rag_result.model_dump()
    _record_policy_decision(state, policy)
    if policy.should_use_retrieved_contexts:
        _attach_rag_result(state, rag_result)

    draft = _compose_policy_or_rag_answer(policy, rag_result)
    state.draft_answer = draft
    state.final_answer = FinalSafetyGuard().enforce(draft)
    _verify_answer(
        state,
        require_citations=rag_result.has_usable_hits and policy.should_require_citations,
        rag_result=rag_result,
    )
    return state


async def run_disease_consultation(
    query: str,
    *,
    rag_client: RagServerClient | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    unsafe_draft_for_test: str | None = None,
) -> AgentState:
    rag_client = rag_client or FakeRagServerClient()
    state = AgentState(
        session_id=session_id or _new_session_id(),
        user_query=query,
        intent="disease_consultation",
        intent_confidence=0.9,
    )
    policy = classify_rag_answer_policy(query)
    safety_precheck = SafetyPrecheck().classify(query)
    if policy.force_safety_refusal:
        state.risk_level = "high"
        state.tool_results["safety_precheck"] = safety_precheck.model_dump()
        rag_query = f"{query} 兽医监督 食品动物 安全边界"
        rag_result = await rag_client.query(rag_query, top_k=4, domain="disease", request_id=request_id)
        state.tool_results["livestock_rag_search"] = rag_result.model_dump()
        _record_policy_decision(state, policy)
        draft = SAFETY_REFUSAL_TEXT
        state.draft_answer = unsafe_draft_for_test if unsafe_draft_for_test is not None else draft
        state.final_answer = FinalSafetyGuard().enforce(state.draft_answer)
        _verify_answer(state, require_citations=False, rag_result=rag_result)
        return state

    slots = SlotExtractor().extract(query)
    state.tool_results["slot_extractor"] = slots.model_dump()
    questions = build_follow_up_questions(slots)
    if questions:
        state.need_follow_up = True
        state.follow_up_questions = questions
        state.final_answer = "请先补充以下信息：\n" + "\n".join(f"- {item}" for item in questions)
        return state

    risk_result = DiseaseRiskEvaluator().evaluate(**slots.model_dump())
    state.risk_level = risk_result.risk_level
    state.tool_results["disease_risk_evaluator"] = risk_result.model_dump()

    rag_query = f"{query} 风险等级 {risk_result.risk_level} 处理原则"
    rag_result = await rag_client.query(rag_query, top_k=4, domain="disease", species=slots.species, request_id=request_id)
    state.tool_results["livestock_rag_search"] = rag_result.model_dump()
    _record_policy_decision(state, policy)
    if policy.should_use_retrieved_contexts:
        _attach_rag_result(state, rag_result)

    if unsafe_draft_for_test is not None:
        draft = unsafe_draft_for_test
    else:
        evidence_answer = AnswerGenerator().compose_with_citations(rag_result)
        draft = (
            f"初步风险等级：{risk_result.risk_level}。\n"
            f"{risk_result.reason}\n"
            f"是否建议联系兽医：{'是' if risk_result.need_vet else '视情况'}。\n\n"
            f"{evidence_answer}"
        )
    state.draft_answer = draft
    state.final_answer = FinalSafetyGuard().enforce(draft)
    _verify_answer(state, require_citations=rag_result.has_usable_hits, rag_result=rag_result)
    return state


async def run_measurement_analysis(
    measurement: MeasurementInput,
    *,
    session_id: str | None = None,
) -> AgentState:
    state = AgentState(
        session_id=session_id or _new_session_id(),
        user_query=f"analyze measurement for {measurement.animal_id}",
        intent="measurement_analysis",
        intent_confidence=0.9,
    )
    result = BodyMeasurementAnalyzer().analyze(measurement)
    state.tool_results["body_measurement_analyzer"] = result.model_dump()
    state.draft_answer = result.report
    state.final_answer = FinalSafetyGuard().enforce(result.report)

    verification = VerifierLite().check(
        state.final_answer or "",
        measurement_abnormal_items=result.abnormal_items,
        measurement_evidence=result.evidence,
    )
    if not verification.passed:
        for issue in verification.issues:
            state.errors.append(AgentToolError(tool_name="verifier_lite", error_code=issue, message=issue))
    return state


def _attach_rag_result(state: AgentState, rag_result: RagSearchResult) -> None:
    if not rag_result.has_usable_hits:
        return
    for hit in rag_result.hits:
        state.retrieved_contexts.append(
            RetrievedContext(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                title=hit.document_title,
                content=hit.content,
                page=hit.page,
                section_title=hit.section_title,
                score=hit.score,
                source_type=hit.metadata.get("source_type"),
            )
        )


def _compose_policy_or_rag_answer(policy: RagAnswerPolicyDecision, rag_result: RagSearchResult) -> str:
    if policy.force_safety_refusal:
        return SAFETY_REFUSAL_TEXT
    if policy.force_no_answer:
        return NO_ANSWER_TEXT
    return AnswerGenerator().compose_with_citations(rag_result)


def _record_policy_decision(state: AgentState, policy: RagAnswerPolicyDecision) -> None:
    if not policy.warning:
        return
    state.tool_results["rag_answer_policy"] = policy.model_dump()


def _verify_answer(
    state: AgentState,
    *,
    require_citations: bool,
    rag_result: RagSearchResult,
) -> None:
    verification = VerifierLite().check(
        state.final_answer or "",
        require_citations=require_citations,
        citations=rag_result.citations,
    )
    if not verification.passed:
        for issue in verification.issues:
            state.errors.append(AgentToolError(tool_name="verifier_lite", error_code=issue, message=issue))


def _new_session_id() -> str:
    return f"s_{uuid4().hex}"
