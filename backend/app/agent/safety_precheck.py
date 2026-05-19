from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SafetyLevel = Literal["S0", "S1", "S2", "S3", "S4"]
SafetyAction = Literal["allow", "allow_with_caution", "escalate", "refuse"]


class SafetyPrecheckResult(BaseModel):
    level: SafetyLevel
    action: SafetyAction
    risk_tags: list[str] = Field(default_factory=list)
    requires_vet: bool = False
    reason: str = ""


class SafetyPrecheck:
    dosage_keywords = (
        "mg/kg",
        "ml/kg",
        "iu/kg",
        "dose",
        "dosage",
        "per kg",
        "每公斤",
        "剂量",
        "用量",
    )
    prescription_keywords = (
        "prescription",
        "prescribe",
        "antibiotic prescription",
        "complete prescription",
        "开处方",
        "开具处方",
        "处方",
        "处方药",
        "抗生素处方",
    )
    definitive_diagnosis_keywords = (
        "definitive diagnosis",
        "guaranteed diagnosis",
        "diagnose as",
        "确诊",
        "确定诊断",
        "诊断为",
        "一定是",
    )
    food_safety_keywords = (
        "food safety",
        "milk withdrawal",
        "meat withdrawal",
        "withdrawal period",
        "withdrawal periods",
        "sell milk",
        "sell meat",
        "食品安全",
        "牛奶出售",
        "卖奶",
        "卖肉",
        "屠宰",
        "休药期",
        "停药期",
    )
    group_outbreak_keywords = (
        "group outbreak",
        "multiple animals",
        "many cattle",
        "群体发病",
        "多头",
        "好几头",
        "整群",
    )
    disease_keywords = (
        "diarrhea",
        "fever",
        "cough",
        "sick",
        "symptom",
        "腹泻",
        "发烧",
        "体温",
        "咳嗽",
        "精神差",
        "不吃",
        "症状",
    )
    husbandry_keywords = (
        "feeding",
        "weaning",
        "body measurement",
        "chest girth",
        "livestock",
        "饲喂",
        "断奶",
        "体尺",
        "胸围",
        "养殖",
    )

    def classify(self, text: str) -> SafetyPrecheckResult:
        normalized = text.lower()
        s4_tags = self._matched_tags(
            normalized,
            {
                "dosage": self.dosage_keywords,
                "prescription": self.prescription_keywords,
                "definitive_diagnosis": self.definitive_diagnosis_keywords,
            },
        )
        if s4_tags:
            return SafetyPrecheckResult(
                level="S4",
                action="refuse",
                risk_tags=s4_tags,
                requires_vet=True,
                reason="hard safety boundary matched",
            )

        s3_tags = self._matched_tags(
            normalized,
            {
                "group_outbreak": self.group_outbreak_keywords,
                "food_safety": self.food_safety_keywords,
            },
        )
        if s3_tags:
            return SafetyPrecheckResult(
                level="S3",
                action="escalate",
                risk_tags=s3_tags,
                requires_vet=True,
                reason="high-risk veterinary or food-safety signal matched",
            )

        if self._contains_any(normalized, self.disease_keywords):
            return SafetyPrecheckResult(
                level="S2",
                action="allow_with_caution",
                risk_tags=["disease_consultation"],
                requires_vet=False,
                reason="disease consultation signal matched",
            )

        if self._contains_any(normalized, self.husbandry_keywords):
            return SafetyPrecheckResult(
                level="S1",
                action="allow",
                risk_tags=["livestock_management"],
                requires_vet=False,
                reason="low-risk livestock management signal matched",
            )

        return SafetyPrecheckResult(level="S0", action="allow", reason="no livestock safety signal matched")

    def _matched_tags(self, text: str, categories: dict[str, tuple[str, ...]]) -> list[str]:
        return [tag for tag, keywords in categories.items() if self._contains_any(text, keywords)]

    def _contains_any(self, text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword.lower() in text for keyword in keywords)
