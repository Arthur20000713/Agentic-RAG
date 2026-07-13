from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SafetyResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
    message: str = ""


class SafetyGuard:
    def __init__(self, rule_path: str | Path | None = None) -> None:
        self.rule_path = Path(rule_path) if rule_path else Path(__file__).parents[1] / "rules" / "safety_rules.yaml"
        self.rules = self._load_rules()

    def check(self, text: str, *, categories: set[str] | None = None) -> SafetyResult:
        violations: list[str] = []
        for category, patterns in self.rules.items():
            if categories is not None and category not in categories:
                continue
            if any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns):
                violations.append(category)
        if violations:
            return SafetyResult(
                passed=False,
                violations=violations,
                message="回答包含疾病安全边界内禁止输出的内容。",
            )
        return SafetyResult(passed=True, message="passed")

    def _load_rules(self) -> dict[str, list[str]]:
        with self.rule_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        blocked = data.get("blocked_categories", {})
        return {key: list(value or []) for key, value in blocked.items()}


class FinalSafetyGuard:
    def __init__(self, safety_guard: SafetyGuard | None = None) -> None:
        self.safety_guard = safety_guard or SafetyGuard()

    def enforce(self, answer: str, *, categories: set[str] | None = None) -> str:
        result = self.safety_guard.check(answer, categories=categories)
        if result.passed:
            return answer
        return (
            "安全提示：不能提供具体药物剂量、处方或确定性诊断。"
            "建议尽快联系执业兽医，并补充体温、持续时间、采食状态、粪便状态和是否群体发病等信息。"
        )
