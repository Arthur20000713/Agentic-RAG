from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from backend.app.agent.graph import run_measurement_graph
from backend.app.agent.rag_answer_policy import SAFETY_REFUSAL_POLICY_WARNING
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.api import ChatRequest as LegacyChatRequest
from backend.app.schemas.internal_v1 import (
    ChatOutcome,
    ChatRequest,
    ChatResponse,
    EvidenceStatus,
    MeasurementAnalysis,
    MeasurementAnalyzeRequest,
    MeasurementAnalyzeResponse,
    OpaqueContext,
    SafetyDecision,
    SourceCitation,
)
from backend.app.schemas.measurement import (
    BodyMeasurementValues,
    MeasurementAnalysisResult,
    MeasurementHistoryItem,
    MeasurementInput,
)
from backend.app.services.chat_service import ChatService, state_to_chat_data
from backend.app.services.trace_service import TraceService


class InternalAiService:
    def __init__(
        self,
        rag_client: RagServerClient,
        settings: Settings,
        trace_service: TraceService | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        memory_store: BaseStore | None = None,
    ) -> None:
        self.rag_client = rag_client
        self.settings = settings
        self.trace_service = trace_service
        self.checkpointer = checkpointer
        self.memory_store = memory_store

    async def chat(self, payload: ChatRequest, *, run_id: str) -> ChatResponse:
        service = ChatService(
            self.rag_client,
            settings=self.settings,
            conversation_history=_conversation_history(payload),
            initial_session_context=dict(payload.context.slots),
            checkpointer=self.checkpointer,
            memory_store=self.memory_store,
            memory_scope_authoritative=payload.animal_snapshot is not None,
            animal_profile=(
                payload.animal_snapshot.model_dump(mode="json")
                if payload.animal_snapshot is not None
                else None
            ),
        )
        state = await service.ask(
            LegacyChatRequest(
                query=payload.query,
                session_id=payload.conversation_id,
                user_id=payload.user_id,
                animal_id=payload.animal_snapshot.animal_id if payload.animal_snapshot else None,
            ),
            request_id=payload.request_id,
        )
        return _chat_response(
            payload,
            state,
            run_id=run_id,
            settings=self.settings,
            trace_id=self._record_trace(state, request_id=payload.request_id),
        )

    async def analyze_measurement(
        self,
        payload: MeasurementAnalyzeRequest,
        *,
        run_id: str,
    ) -> MeasurementAnalyzeResponse:
        measurement = MeasurementInput(
            animal_id=payload.animal_snapshot.animal_id,
            age_month=payload.age_month,
            current=BodyMeasurementValues.model_validate(payload.current.model_dump()),
            history=[
                MeasurementHistoryItem.model_validate(item.model_dump())
                for item in payload.history
            ],
            confidence=payload.confidence,
            use_demo_history=payload.use_demo_history,
        )
        state = await run_measurement_graph(
            measurement,
            session_id=payload.operation_id,
            request_id=payload.request_id,
            user_id=payload.user_id,
            animal_profile=payload.animal_snapshot.model_dump(mode="json"),
            memory_scope_authoritative=True,
            checkpointer=self.checkpointer,
            store=self.memory_store,
            settings=self.settings,
        )
        result = MeasurementAnalysisResult.model_validate(state.measurement_report)
        if payload.confidence is not None and payload.confidence < 0.6:
            outcome = "LOW_CONFIDENCE"
        elif not payload.history:
            outcome = "INSUFFICIENT_DATA"
        else:
            outcome = "ANALYZED"
        return MeasurementAnalyzeResponse(
            request_id=payload.request_id,
            operation_id=payload.operation_id,
            run_id=run_id,
            outcome=outcome,
            result=MeasurementAnalysis.model_validate(result.model_dump()),
            trace_id=self._record_trace(state, request_id=payload.request_id),
        )

    def _record_trace(self, state: MultiAgentState, *, request_id: str) -> str:
        if self.trace_service is None:
            return _trace_id(f"run_{request_id}")
        trace_id = self.trace_service.record_agent_trace(
            session_id=state.session_id,
            request_id=request_id,
            trace=state.agent_trace,
            status="failed" if state.errors else "success",
        )
        return f"agent_trace_{trace_id}"


def _conversation_history(payload: ChatRequest) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for item in payload.history:
        if item.role == "USER":
            history.append({"user": item.content, "assistant": ""})
            continue
        if not history or history[-1].get("assistant"):
            history.append({"user": "", "assistant": item.content})
        else:
            history[-1]["assistant"] = item.content
    return history


def _chat_response(
    payload: ChatRequest,
    state: MultiAgentState,
    *,
    run_id: str,
    settings: Settings,
    trace_id: str,
) -> ChatResponse:
    evidence_status = _evidence_status(state)
    safety = _safety_decision(state)
    follow_up_questions = _follow_up_questions(state)
    if safety.decision == "REFUSED":
        outcome = ChatOutcome.SAFETY_REFUSAL
    elif follow_up_questions:
        outcome = ChatOutcome.NEEDS_FOLLOW_UP
    elif evidence_status in {
        EvidenceStatus.LOW_CONFIDENCE,
        EvidenceStatus.EMPTY,
        EvidenceStatus.UNAVAILABLE,
    } and state.intent in {"general_qa", "disease_consultation"}:
        outcome = ChatOutcome.LOW_CONFIDENCE
    else:
        outcome = ChatOutcome.ANSWERED

    source_payload = state_to_chat_data(state, settings=settings).get("sources") or []
    sources = (
        _source_citations(state, source_payload, collection=settings.rag_server.collection)
        if evidence_status == EvidenceStatus.SUPPORTED and safety.decision == "ALLOWED"
        else []
    )
    return ChatResponse(
        request_id=payload.request_id,
        operation_id=payload.operation_id,
        run_id=run_id,
        outcome=outcome,
        answer=state.final_answer or "当前无法生成回答，请稍后重试。",
        intent=state.intent or "out_of_scope",
        risk_level=_risk_level(state.risk_level),
        evidence_status=evidence_status,
        sources=sources,
        follow_up_questions=follow_up_questions,
        tools_used=list(dict.fromkeys(str(name) for name in state.tool_results)),
        safety=safety,
        next_context=_next_context(payload.context, state),
        context_version=payload.context_version + 1,
        trace_id=trace_id,
    )


def _evidence_status(state: MultiAgentState) -> EvidenceStatus:
    if state.intent not in {"general_qa", "disease_consultation"}:
        return EvidenceStatus.NOT_REQUIRED
    return {
        "success": EvidenceStatus.SUPPORTED,
        "low_confidence": EvidenceStatus.LOW_CONFIDENCE,
        "empty": EvidenceStatus.EMPTY,
        "error": EvidenceStatus.UNAVAILABLE,
    }.get(state.evidence_status, EvidenceStatus.UNAVAILABLE)


def _safety_decision(state: MultiAgentState) -> SafetyDecision:
    policy = state.tool_results.get("rag_answer_policy")
    if isinstance(policy, dict) and policy.get("warning") == SAFETY_REFUSAL_POLICY_WARNING:
        return SafetyDecision(decision="REFUSED", reason_code="POLICY_REFUSAL")
    result = state.safety_result if isinstance(state.safety_result, dict) else {}
    passed = bool(result.get("passed", True))
    violations = [str(item) for item in result.get("violations") or []]
    return SafetyDecision(
        decision="ALLOWED" if passed else "REFUSED",
        reason_code=violations[0] if violations else None,
    )


def _follow_up_questions(state: MultiAgentState) -> list[str]:
    for key in ("disease_reasoning", "disease_reasoning_shadow"):
        record = state.tool_results.get(key)
        reasoning = record.get("reasoning") if isinstance(record, dict) else None
        if isinstance(reasoning, dict) and reasoning.get("follow_up_questions"):
            return [
                str(item)
                for item in reasoning["follow_up_questions"]
                if str(item).strip()
            ][:10]
    assessment = state.disease_assessment if isinstance(state.disease_assessment, dict) else {}
    raw = assessment.get("follow_up_questions") or state.session_context.get("pending_questions") or []
    return [str(item) for item in raw if str(item).strip()][:10]


def _risk_level(value: str | None) -> str:
    return {
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
        "emergency": "CRITICAL",
    }.get(value, "LOW")


def _source_citations(
    state: MultiAgentState,
    sources: list[dict[str, Any]],
    *,
    collection: str,
) -> list[SourceCitation]:
    contexts = {item.chunk_id: item for item in state.retrieved_contexts}
    mapped: list[SourceCitation] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        chunk_id = source.get("chunk_id")
        context = contexts.get(str(chunk_id)) if chunk_id is not None else None
        if context is None or context.document_id is None or not context.title:
            continue
        page = source.get("page", context.page)
        if page is not None and int(page) < 1:
            page = None
        mapped.append(
            SourceCitation(
                collection=collection,
                document_id=context.document_id,
                title=context.title,
                source_uri=source.get("source_uri"),
                page=page,
                section_title=source.get("section_title") or context.section_title,
                chunk_id=context.chunk_id,
                score=max(0.0, min(float(context.score), 1.0)),
            )
        )
    return mapped


def _next_context(previous: OpaqueContext, state: MultiAgentState) -> OpaqueContext:
    root = previous.model_dump(by_alias=True)
    slots = dict(previous.slots)
    slots.update(
        {
            key: value
            for key, value in state.session_context.items()
            if key not in {"conversation_history", "session_id"}
        }
    )
    root["schemaVersion"] = previous.schema_version
    root["slots"] = slots
    return OpaqueContext.model_validate(root)


def _trace_id(run_id: str) -> str:
    return f"trace_{run_id.removeprefix('run_')}"
