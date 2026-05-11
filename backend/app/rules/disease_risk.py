from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "emergency"]


class DiseaseRiskResult(BaseModel):
    risk_level: RiskLevel = "medium"
    need_vet: bool = False
    need_isolation: bool = False
    missing_info: list[str] = Field(default_factory=list)
    reason: str
    status: Literal["success", "missing_info"] = "success"


class DiseaseRiskEvaluator:
    def __init__(self, rule_path: str | Path | None = None) -> None:
        self.rule_path = Path(rule_path) if rule_path else Path(__file__).with_name("disease_risk.yaml")
        self.rules = self._load_rules()

    def evaluate(
        self,
        *,
        species: str | None = None,
        age_stage: str | None = None,
        symptoms: list[str] | None = None,
        temperature_c: float | None = None,
        duration_days: float | None = None,
        group_outbreak: bool | None = None,
    ) -> DiseaseRiskResult:
        symptoms = symptoms or []
        missing_info = self._missing_info(
            species=species,
            symptoms=symptoms,
            temperature_c=temperature_c,
            duration_days=duration_days,
            group_outbreak=group_outbreak,
        )
        if missing_info:
            return DiseaseRiskResult(
                status="missing_info",
                risk_level="medium",
                need_vet=False,
                need_isolation=False,
                missing_info=missing_info,
                reason="关键信息不足，暂按中等风险保守处理，并建议补充信息。",
            )

        normalized_symptoms = {item.strip().lower() for item in symptoms}
        emergency_symptoms = {item.lower() for item in self.rules["emergency_symptoms"]}
        high_risk_symptoms = {item.lower() for item in self.rules["high_risk_symptoms"]}

        has_emergency_symptom = bool(normalized_symptoms & emergency_symptoms)
        has_high_risk_symptom = bool(normalized_symptoms & high_risk_symptoms)
        has_fever = temperature_c is not None and temperature_c >= float(self.rules["fever_threshold_c"])
        has_long_duration = duration_days is not None and duration_days >= float(self.rules["high_duration_days"])

        if group_outbreak and has_emergency_symptom:
            return DiseaseRiskResult(
                risk_level="emergency",
                need_vet=True,
                need_isolation=True,
                reason="出现群体发病或疑似急性严重症状，应立即隔离并联系兽医现场处理。",
            )
        if has_fever and has_long_duration and has_high_risk_symptom:
            return DiseaseRiskResult(
                risk_level="high",
                need_vet=True,
                need_isolation=bool(group_outbreak),
                reason="持续症状伴随发热和采食或精神异常，风险较高，需要尽快人工检查。",
            )
        if has_high_risk_symptom or has_fever:
            return DiseaseRiskResult(
                risk_level="medium",
                need_vet=False,
                need_isolation=bool(group_outbreak),
                reason="存在可疑症状，建议补充观察体温、采食、粪便和群体情况。",
            )
        return DiseaseRiskResult(
            risk_level="low",
            need_vet=False,
            need_isolation=False,
            reason="当前信息未触发高风险规则，建议继续观察并记录变化。",
        )

    def _missing_info(
        self,
        *,
        species: str | None,
        symptoms: list[str],
        temperature_c: float | None,
        duration_days: float | None,
        group_outbreak: bool | None,
    ) -> list[str]:
        values = {
            "species": species,
            "symptoms": symptoms,
            "temperature_c": temperature_c,
            "duration_days": duration_days,
            "group_outbreak": group_outbreak,
        }
        missing: list[str] = []
        for field in self.rules["required_slots"]:
            value = values[field]
            if value is None or value == "" or value == []:
                missing.append(field)
        return missing

    def _load_rules(self) -> dict:
        with self.rule_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return {
            "required_slots": data.get("required_slots", []),
            "fever_threshold_c": data.get("fever_threshold_c", 40.0),
            "high_duration_days": data.get("high_duration_days", 2),
            "emergency_symptoms": data.get("emergency_symptoms", []),
            "high_risk_symptoms": data.get("high_risk_symptoms", []),
        }

