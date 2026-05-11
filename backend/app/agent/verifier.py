from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.agent.safety import SafetyGuard
from backend.app.schemas.rag_server import RagCitation


class VerificationResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)


class VerifierLite:
    def __init__(self, safety_guard: SafetyGuard | None = None) -> None:
        self.safety_guard = safety_guard or SafetyGuard()

    def check(
        self,
        answer: str,
        *,
        require_citations: bool = False,
        citations: list[RagCitation] | list[dict] | None = None,
        measurement_abnormal_items: list[str] | None = None,
        measurement_evidence: list[str] | None = None,
    ) -> VerificationResult:
        issues: list[str] = []
        safety = self.safety_guard.check(answer)
        issues.extend(safety.violations)

        if require_citations and not citations:
            issues.append("missing_citation")

        if measurement_abnormal_items and not measurement_evidence:
            issues.append("measurement_missing_evidence")

        return VerificationResult(passed=not issues, issues=issues)

