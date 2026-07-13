from __future__ import annotations

import time

from backend.app.agent.safety import FinalSafetyGuard, SafetyGuard
from backend.app.agent.state import MultiAgentState
from backend.app.schemas.agent import AgentToolError


S4_HARD_VIOLATIONS = {"dosage", "prescription", "definitive_diagnosis"}
GENERAL_CHAT_SAFETY_CATEGORIES = {"fabricated_tool_result"}


class SafetyAgent:
    def __init__(
        self,
        *,
        safety_guard: SafetyGuard | None = None,
        final_safety_guard: FinalSafetyGuard | None = None,
    ) -> None:
        self.safety_guard = safety_guard or SafetyGuard()
        self.final_safety_guard = final_safety_guard or FinalSafetyGuard(self.safety_guard)

    def check(self, state: MultiAgentState) -> MultiAgentState:
        started_at = time.perf_counter()
        state.active_agent = "safety_agent"

        candidate_answer = state.final_answer or state.draft_answer or ""
        categories = None if state.intent == "disease_consultation" else GENERAL_CHAT_SAFETY_CATEGORIES
        result = self.safety_guard.check(candidate_answer, categories=categories)
        hard_violations = [violation for violation in result.violations if violation in S4_HARD_VIOLATIONS]
        safe_answer = (
            candidate_answer
            if result.passed
            else self.final_safety_guard.enforce(candidate_answer, categories=categories)
        )
        state.final_answer = safe_answer
        state.safety_result = {
            "passed": result.passed,
            "violations": result.violations,
            "hard_blocked": bool(hard_violations),
            "hard_violations": hard_violations,
            "message": result.message,
            "safe_answer": safe_answer,
        }
        state.tool_results["safety_agent"] = state.safety_result

        if not result.passed:
            for violation in result.violations:
                state.errors.append(
                    AgentToolError(
                        tool_name="safety_agent",
                        error_code=violation,
                        message=result.message or violation,
                    )
                )

        state.agent_trace.append(
            {
                "node": "safety_agent",
                "status": "success" if result.passed else "blocked",
                "passed": result.passed,
                "violations": result.violations,
                "hard_blocked": bool(hard_violations),
                "violation_count": len(result.violations),
                "latency_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
            }
        )
        return state
