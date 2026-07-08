from __future__ import annotations

from typing import Any

from backend.app.agent.graph import run_disease_graph, run_general_qa_graph
from backend.app.agent.router import IntentRouter
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.agent.workflow import run_disease_consultation, run_general_qa
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.agent import AgentState
from backend.app.schemas.api import ChatRequest
from backend.app.services.feature_flag_service import FeatureFlagService, FeatureFlagSnapshot
from backend.app.services.session_context_service import SessionContextService


ASSISTANT_INTRO_ANSWER = (
    "你好，我是 Livestock Agentic RAG 智能助手，主要面向畜牧业知识问答、疾病初步问诊、"
    "体尺分析和资料检索。你可以问我牛、羊、猪等养殖管理、饲喂、断奶、常见症状处理、"
    "资料依据和引用来源类问题；非畜牧领域的问题我会明确说明不在服务范围内。"
)


class ChatService:
    def __init__(
        self,
        rag_client: RagServerClient,
        settings: Settings | None = None,
        session_context_service: SessionContextService | None = None,
    ) -> None:
        self.rag_client = rag_client
        self.settings = settings or Settings()
        self.session_context_service = session_context_service
        self.router = IntentRouter()

    async def ask(self, request: ChatRequest, *, request_id: str | None = None) -> AgentState | MultiAgentState:
        route = self.router.route(request.query)
        if route.intent == "assistant_intro":
            return self._assistant_intro_state(request, confidence=route.confidence)
        if FeatureFlagService(self.settings).v3_enabled:
            if route.intent == "disease_consultation":
                return await run_disease_graph(
                    request.query,
                    rag_client=self.rag_client,
                    session_context_service=self.session_context_service,
                    session_id=request.session_id,
                    request_id=request_id,
                    settings=self.settings,
                )
            if route.intent == "general_qa":
                return await run_general_qa_graph(
                    request.query,
                    rag_client=self.rag_client,
                    session_id=request.session_id,
                    request_id=request_id,
                    settings=self.settings,
                )
        if route.intent == "disease_consultation":
            return await run_disease_consultation(
                request.query,
                rag_client=self.rag_client,
                session_id=request.session_id,
                request_id=request_id,
            )
        if route.intent == "general_qa":
            return await run_general_qa(
                request.query,
                rag_client=self.rag_client,
                session_id=request.session_id,
                request_id=request_id,
            )
        state = AgentState(
            session_id=request.session_id or "s_api",
            user_query=request.query,
            intent=route.intent,
            intent_confidence=route.confidence,
        )
        if route.intent == "measurement_analysis":
            state.final_answer = "请使用 /api/measurement/analyze 提交结构化体尺数据。"
        else:
            state.final_answer = "当前问题超出畜牧业辅助问答范围。"
        return state

    def _assistant_intro_state(self, request: ChatRequest, *, confidence: float) -> AgentState:
        return AgentState(
            session_id=request.session_id or "s_api",
            user_query=request.query,
            intent="assistant_intro",
            intent_confidence=confidence,
            final_answer=ASSISTANT_INTRO_ANSWER,
        )


def state_to_chat_data(state: AgentState | MultiAgentState, *, settings: Settings | None = None) -> dict:
    return {
        "answer": state.final_answer,
        "intent": state.intent,
        "risk_level": state.risk_level,
        "sources": _state_sources(state),
        "tools_used": list(state.tool_results),
        "need_follow_up": getattr(state, "need_follow_up", False),
        "follow_up_questions": getattr(state, "follow_up_questions", []),
        "errors": [error.model_dump() for error in state.errors],
        "v3_debug": build_debug_payload(settings, state=state),
    }


def build_debug_payload(settings: Settings | None = None, *, state: AgentState | MultiAgentState | None = None) -> dict:
    snapshot = FeatureFlagService(settings or Settings()).snapshot()
    payload: dict[str, Any] = {
        "v3_enabled": snapshot.v3_enabled,
        "flags": snapshot.model_dump(),
        "rag_status": build_rag_status_payload(settings or Settings()),
    }
    if isinstance(state, MultiAgentState):
        payload.update(
            {
                "agent_path": [item.get("node") for item in state.agent_trace if item.get("node")],
                "safety": state.safety_result,
                "verifier": state.verification_result,
                "evidence_status": state.evidence_status,
                "model_fallbacks": list(state.tool_results.get("model_fallbacks") or []),
            }
        )
    return payload


def build_rag_status_payload(settings: Settings) -> dict:
    rag_settings = settings.rag_server
    collection = rag_settings.collection
    batch_summary = v4_2_quality_summary(collection=collection, real_configured=bool(rag_settings.repo_path))
    return {
        "rag_mode": rag_settings.normalized_query_mode,
        "collection": collection,
        "batch_id": batch_summary["batch_id"],
        "quality_gate_status": batch_summary["quality_gate_status"],
    }


def v4_2_quality_summary(*, collection: str, real_configured: bool) -> dict:
    if collection != "livestock_v4_2":
        return {"batch_id": None, "quality_gate_status": "not_configured"}
    batch_id = "batch_002"
    if not real_configured:
        return {"batch_id": batch_id, "quality_gate_status": "not_configured"}
    report_path = PROJECT_ROOT / "docs" / "rag_corpus" / "reports" / "batch_002_quality.md"
    if not report_path.exists():
        return {"batch_id": batch_id, "quality_gate_status": "missing_report"}
    text = report_path.read_text(encoding="utf-8").lower()
    if "quality gate: not evaluated" in text:
        return {"batch_id": batch_id, "quality_gate_status": "not_evaluated"}
    if "quality gate: passed" in text:
        return {"batch_id": batch_id, "quality_gate_status": "passed"}
    if "quality gate: failed" in text:
        return {"batch_id": batch_id, "quality_gate_status": "failed"}
    return {"batch_id": batch_id, "quality_gate_status": "unknown"}


def _state_sources(state: AgentState | MultiAgentState) -> list[dict]:
    rag_result = state.tool_results.get("livestock_rag_search")
    if isinstance(rag_result, dict) and rag_result.get("status") == "success":
        hits = list(rag_result.get("hits") or [])
        sources: list[dict] = []
        seen: set[str] = set()
        for citation in rag_result.get("citations") or []:
            if not isinstance(citation, dict):
                continue
            hit = _matching_hit(citation, hits)
            source_uri = citation.get("source_uri") or (hit or {}).get("source_uri")
            key = source_uri or "|".join(
                str(citation.get(field) or "")
                for field in ("source_id", "chunk_id", "title", "page")
            )
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "source_uri": source_uri,
                    "title": citation.get("title") or (hit or {}).get("document_title"),
                    "page": citation.get("page"),
                    "section_title": citation.get("section_title"),
                    "chunk_id": citation.get("chunk_id") or (hit or {}).get("chunk_id"),
                }
            )
        return sources

    return [
        {
            "source_uri": None,
            "title": item.title,
            "page": item.page,
            "section_title": item.section_title,
            "chunk_id": item.chunk_id,
        }
        for item in state.retrieved_contexts
    ]


def _matching_hit(citation: dict, hits: list[dict]) -> dict | None:
    chunk_id = citation.get("chunk_id")
    if chunk_id:
        for hit in hits:
            if hit.get("chunk_id") == chunk_id:
                return hit

    source_id = citation.get("source_id")
    title = citation.get("title")
    for hit in hits:
        if source_id is not None and str(hit.get("document_id")) == str(source_id):
            return hit
        if title and hit.get("document_title") == title:
            return hit
    return None
