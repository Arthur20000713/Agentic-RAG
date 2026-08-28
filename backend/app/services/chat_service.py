from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from backend.app.agent.graph import run_chat_graph
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.schemas.api import ChatRequest
from backend.app.services.feature_flag_service import FeatureFlagService
from backend.app.services.session_context_service import SessionContextService

class ChatService:
    def __init__(
        self,
        rag_client: RagServerClient,
        settings: Settings | None = None,
        session_context_service: SessionContextService | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        initial_session_context: dict[str, Any] | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        memory_store: BaseStore | None = None,
        memory_scope_authoritative: bool = False,
        animal_profile: dict[str, Any] | None = None,
    ) -> None:
        self.rag_client = rag_client
        self.settings = settings or Settings()
        self.session_context_service = session_context_service
        self.conversation_history = list(conversation_history or [])
        self.initial_session_context = dict(initial_session_context or {})
        self.checkpointer = checkpointer
        self.memory_store = memory_store
        self.memory_scope_authoritative = memory_scope_authoritative
        self.animal_profile = dict(animal_profile or {}) or None

    async def ask(self, request: ChatRequest, *, request_id: str | None = None) -> MultiAgentState:
        return await run_chat_graph(
            request.query,
            rag_client=self.rag_client,
            session_context_service=self.session_context_service,
            session_id=request.session_id,
            request_id=request_id,
            user_id=request.user_id,
            animal_id=request.animal_id,
            animal_profile=self.animal_profile,
            memory_scope_authoritative=self.memory_scope_authoritative,
            checkpointer=self.checkpointer,
            store=self.memory_store,
            settings=self.settings,
            conversation_history=self.conversation_history,
            initial_session_context=self.initial_session_context,
        )


def state_to_chat_data(state: MultiAgentState, *, settings: Settings | None = None) -> dict:
    return {
        "session_id": state.session_id,
        "answer": state.final_answer,
        "intent": state.intent,
        "risk_level": state.risk_level,
        "sources": _state_sources(state),
        "tools_used": list(state.tool_results),
        "need_follow_up": getattr(state, "need_follow_up", False),
        "follow_up_questions": getattr(state, "follow_up_questions", []),
        "errors": [error.model_dump() for error in state.errors],
        "agent_runtime_debug": build_agent_runtime_debug_payload(settings, state=state),
    }


def build_agent_runtime_debug_payload(
    settings: Settings | None = None,
    *,
    state: MultiAgentState | None = None,
) -> dict:
    snapshot = FeatureFlagService(settings or Settings()).snapshot()
    payload: dict[str, Any] = {
        "engine": snapshot.agent_runtime_engine,
        "flags": snapshot.model_dump(),
        "rag_status": build_rag_status_payload(settings or Settings()),
        "disease_llm": _disease_llm_debug_summary(settings or Settings(), state),
    }
    if isinstance(state, MultiAgentState):
        payload.update(
            {
                "orchestration_engine": "langgraph",
                "agent_path": [item.get("node") for item in state.agent_trace if item.get("node")],
                "safety": state.safety_result,
                "verifier": state.verification_result,
                "evidence_status": state.evidence_status,
                "model_fallbacks": list(state.tool_results.get("model_fallbacks") or []),
            }
        )
    return payload


def _disease_llm_debug_summary(settings: Settings, state: MultiAgentState | None) -> dict:
    summary: dict[str, Any] = {
        "enabled": FeatureFlagService(settings).disease_llm_enabled,
        "shadow_mode": bool(settings.disease_llm.shadow_mode),
        "understanding": {"status": "not_available"},
        "evidence_gate": {"status": "not_available"},
        "reasoning": {"status": "not_available"},
        "takeover": {"applied": False},
    }
    if not isinstance(state, MultiAgentState):
        return summary

    understanding = _first_tool_result(state, "disease_understanding", "disease_understanding_shadow")
    if understanding is not None:
        fallback_used = bool(understanding.get("fallback_used"))
        summary["understanding"] = {
            "status": "fallback" if fallback_used else "success",
            "fallback_used": fallback_used,
            "fallback_reason": understanding.get("fallback_reason"),
        }

    gate = state.tool_results.get("disease_evidence_gate")
    if isinstance(gate, dict):
        summary["evidence_gate"] = {
            "status": "passed" if gate.get("allowed") else "blocked",
            "allowed": bool(gate.get("allowed")),
            "error_code": gate.get("error_code"),
            "evidence_ref_count": len(gate.get("evidence_refs") or []),
        }

    reasoning = _first_tool_result(state, "disease_reasoning", "disease_reasoning_shadow")
    if reasoning is not None:
        summary["reasoning"] = {
            "status": reasoning.get("status") or "unknown",
            "fallback_used": bool(reasoning.get("fallback_used")),
            "fallback_reason": reasoning.get("fallback_reason"),
        }

    takeover = state.tool_results.get("disease_reasoning_takeover")
    if isinstance(takeover, dict):
        summary["takeover"] = {"applied": bool(takeover.get("applied"))}
    return summary


def _first_tool_result(state: MultiAgentState, *names: str) -> dict[str, Any] | None:
    for name in names:
        value = state.tool_results.get(name)
        if isinstance(value, dict):
            return value
    return None


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


def _state_sources(state: MultiAgentState) -> list[dict]:
    response_payload = state.tool_results.get("response_agent")
    if isinstance(response_payload, dict) and isinstance(response_payload.get("sources"), list):
        return list(response_payload["sources"])
    if state.evidence_status != "success":
        return []
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
