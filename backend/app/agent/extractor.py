from __future__ import annotations

import re

from pydantic import BaseModel, Field


class DiseaseSlots(BaseModel):
    species: str | None = None
    age_stage: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    temperature_c: float | None = None
    duration_days: float | None = None
    group_outbreak: bool | None = None


class SlotExtractor:
    def extract(self, query: str) -> DiseaseSlots:
        symptoms: list[str] = []
        if "腹泻" in query or "拉稀" in query:
            symptoms.append("diarrhea")
        if "精神差" in query or "精神沉郁" in query:
            symptoms.append("depression")
        if "不吃" in query or "不吃草" in query or "采食下降" in query:
            symptoms.append("low_appetite")
        if "咳嗽" in query:
            symptoms.append("cough")
        if "呼吸困难" in query:
            symptoms.append("breathing_difficulty")

        for symptom in self._extract_tag_values(query, "symptom"):
            if symptom not in symptoms:
                symptoms.append(symptom)

        return DiseaseSlots(
            species=self._extract_tag_value(query, "species") or self._extract_species(query),
            age_stage=self._extract_age_stage(query),
            symptoms=symptoms,
            temperature_c=self._extract_tag_float(query, "temperature_c") or self._extract_temperature(query),
            duration_days=self._extract_tag_float(query, "duration_days") or self._extract_duration_days(query),
            group_outbreak=self._extract_group_outbreak_with_tag(query),
        )

    def _extract_tag_value(self, query: str, field: str) -> str | None:
        match = re.search(rf"\[{re.escape(field)}=([^\]]+)\]", query)
        return match.group(1).strip() if match else None

    def _extract_tag_values(self, query: str, field: str) -> list[str]:
        return [value.strip() for value in re.findall(rf"\[{re.escape(field)}=([^\]]+)\]", query) if value.strip()]

    def _extract_tag_float(self, query: str, field: str) -> float | None:
        value = self._extract_tag_value(query, field)
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _extract_tag_bool(self, query: str, field: str) -> bool | None:
        value = self._extract_tag_value(query, field)
        if value is None:
            return None
        normalized = value.lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        return None

    def _extract_group_outbreak_with_tag(self, query: str) -> bool | None:
        if self._extract_tag_value(query, "group_outbreak") is not None:
            return self._extract_tag_bool(query, "group_outbreak")
        return self._extract_group_outbreak(query)

    def _extract_species(self, query: str) -> str | None:
        if "牛" in query or "牦牛" in query or "犊牛" in query:
            return "cattle"
        if "羊" in query:
            return "sheep"
        if "猪" in query:
            return "pig"
        return None

    def _extract_age_stage(self, query: str) -> str | None:
        if "犊牛" in query or "牛犊" in query:
            return "calf"
        return None

    def _extract_temperature(self, query: str) -> float | None:
        if "正常体温" in query or "体温正常" in query or "没发烧" in query or "没有发烧" in query:
            return 39.0
        match = re.search(r"体温\s*(\d+(?:\.\d+)?)\s*(?:度|℃|c|C)?", query)
        if match:
            return float(match.group(1))
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:度|℃)\s*", query)
        if match:
            value = float(match.group(1))
            if 35 <= value <= 43:
                return value
        return None

    def _extract_duration_days(self, query: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*天", query)
        if match:
            return float(match.group(1))
        if "两天" in query or "二天" in query:
            return 2
        if "一天" in query:
            return 1
        return None

    def _extract_group_outbreak(self, query: str) -> bool | None:
        if "就一只" in query or "只有一只" in query or "单只" in query or "一只这样" in query:
            return False
        if "没有群体发病" in query or "未群体发病" in query or "不是群体" in query:
            return False
        if "群体发病" in query or "多头" in query or "好几头" in query:
            return True
        return None


def build_follow_up_questions(slots: DiseaseSlots) -> list[str]:
    questions: list[str] = []
    if slots.duration_days is None:
        questions.append("症状已经持续多久了？")
    if slots.temperature_c is None:
        questions.append("目前体温是多少？")
    if slots.group_outbreak is None:
        questions.append("是否有群体发病或多头同时出现类似症状？")
    if not slots.symptoms:
        questions.append("主要症状有哪些，例如腹泻、咳嗽、精神差或采食下降？")
    return questions[:3]
