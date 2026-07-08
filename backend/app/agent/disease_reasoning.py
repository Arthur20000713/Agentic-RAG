from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from backend.app.agent.disease_understanding import _run_coroutine_sync
from backend.app.agent.state import MultiAgentState
from backend.app.core.config import Settings
from backend.app.model.primary_llm import PrimaryLLMClient, PrimaryLLMRequest


class DiseaseEvidenceRef(BaseModel):
    source_uri: str
    chunk_id: str


class DiseaseReasoningItem(BaseModel):
    text: str
    evidence_refs: list[DiseaseEvidenceRef] = Field(min_length=1)


class DiseaseReasoningResult(BaseModel):
    status: Literal["success"] = "success"
    schema_name: Literal["disease_reasoning"] = "disease_reasoning"
    contributing_factors: list[DiseaseReasoningItem] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    safe_actions: list[DiseaseReasoningItem] = Field(default_factory=list)
    vet_triggers: list[DiseaseReasoningItem] = Field(default_factory=list)
    not_diagnosis_notice: str


class DiseaseReasoningAgent:
    def __init__(self, settings: Settings | None = None, primary_llm_client: Any | None = None) -> None:
        self.settings = settings or Settings()
        self.primary_llm_client = primary_llm_client or PrimaryLLMClient(self.settings)

    def run(self, state: MultiAgentState) -> MultiAgentState:
        if not self.settings.disease_llm.enabled:
            return state

        started_at = time.perf_counter()
        key = "disease_reasoning_shadow" if self.settings.disease_llm.shadow_mode else "disease_reasoning"
        gate = self._gate(state)
        if self.settings.disease_llm.require_rag_evidence and not gate.get("allowed"):
            record = {
                "status": "blocked",
                "fallback_used": True,
                "fallback_reason": f"evidence_gate_blocked:{gate.get('error_code') or 'unknown'}",
                "reasoning": None,
            }
            self._record(state, key=key, record=record, started_at=started_at)
            return state

        try:
            payload = self._call_llm(state)
            reasoning = DiseaseReasoningResult.model_validate(payload)
            self._validate_refs(reasoning, gate)
            record = {
                "status": "success",
                "fallback_used": False,
                "fallback_reason": None,
                "reasoning": reasoning.model_dump(),
            }
        except (ValidationError, ValueError):
            record = {
                "status": "fallback",
                "fallback_used": True,
                "fallback_reason": "schema_validation_failed",
                "reasoning": None,
            }
        except Exception as exc:
            record = {
                "status": "fallback",
                "fallback_used": True,
                "fallback_reason": f"reasoning_error:{exc.__class__.__name__}",
                "reasoning": None,
            }

        self._record(state, key=key, record=record, started_at=started_at)
        return state

    def _call_llm(self, state: MultiAgentState) -> dict[str, Any]:
        request = PrimaryLLMRequest(
            prompt=self._prompt(state),
            schema_name="disease_reasoning",
            context={
                "session_id": state.session_id,
                "slots": state.extracted_slots,
                "disease_assessment": state.disease_assessment,
                "evidence_gate": self._gate(state),
                "rag_result": state.tool_results.get("livestock_rag_search"),
            },
            system_prompt=(
                "You provide livestock disease consultation reasoning. "
                "Return one JSON object matching disease_reasoning. "
                "Do not diagnose. Do not prescribe drugs or dosages. "
                "Every contributing factor, safe action, and vet trigger must cite evidence_refs."
            ),
        )
        return _run_coroutine_sync(self.primary_llm_client.generate_json(request))

    def _prompt(self, state: MultiAgentState) -> str:
        return (
            "Use only the provided RAG evidence to draft non-diagnostic livestock consultation reasoning. "
            "Bind every item to source_uri and chunk_id from the evidence gate."
        )

    def _gate(self, state: MultiAgentState) -> dict[str, Any]:
        gate = state.tool_results.get("disease_evidence_gate")
        return gate if isinstance(gate, dict) else {"allowed": False, "error_code": "EVIDENCE_GATE_MISSING"}

    def _validate_refs(self, reasoning: DiseaseReasoningResult, gate: dict[str, Any]) -> None:
        allowed_refs = {
            (str(ref.get("source_uri")), str(ref.get("chunk_id")))
            for ref in gate.get("evidence_refs") or []
            if isinstance(ref, dict) and ref.get("source_uri") and ref.get("chunk_id")
        }
        if not allowed_refs:
            raise ValueError("no allowed evidence refs")
        for item in [*reasoning.contributing_factors, *reasoning.safe_actions, *reasoning.vet_triggers]:
            for ref in item.evidence_refs:
                if (ref.source_uri, ref.chunk_id) not in allowed_refs:
                    raise ValueError("reasoning item uses evidence ref outside gate")

    def _record(self, state: MultiAgentState, *, key: str, record: dict[str, Any], started_at: float) -> None:
        state.tool_results[key] = record
        state.agent_trace.append(
            {
                "node": "disease_reasoning_agent",
                "status": record["status"],
                "shadow_mode": self.settings.disease_llm.shadow_mode,
                "fallback_used": record["fallback_used"],
                "fallback_reason": record["fallback_reason"],
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
