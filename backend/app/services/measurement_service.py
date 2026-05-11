from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.app.schemas.measurement import MeasurementAnalysisResult, MeasurementInput
from backend.app.db.repositories import MeasurementRepository


class MeasurementService:
    def __init__(self, measurement_repository: MeasurementRepository | None = None) -> None:
        self.measurement_repository = measurement_repository
        self.analyzer = BodyMeasurementAnalyzer()

    def analyze(self, measurement: MeasurementInput) -> MeasurementAnalysisResult:
        history = list(measurement.history)
        used_demo_history = measurement.use_demo_history
        if not history and self.measurement_repository is not None:
            history = self.measurement_repository.list_history(measurement.animal_id)
        if not history and measurement.use_demo_history:
            history = self._demo_history(measurement)

        enriched = MeasurementInput(
            animal_id=measurement.animal_id,
            age_month=measurement.age_month,
            current=measurement.current,
            history=history,
            confidence=measurement.confidence,
            use_demo_history=used_demo_history and bool(history),
        )
        return self.analyzer.analyze(enriched)

    def _demo_history(self, measurement: MeasurementInput) -> list[dict]:
        current = measurement.current.model_dump()
        demo: dict = {"measure_date": "2026-04-01"}
        if current.get("chest_girth_cm") is not None:
            demo["chest_girth_cm"] = max(float(current["chest_girth_cm"]) - 1.4, 0)
        if current.get("weight_kg") is not None:
            demo["weight_kg"] = max(float(current["weight_kg"]) - 4.5, 0)
        if len(demo) == 1:
            demo["body_height_cm"] = 110.0
        return [demo]


class BodyMeasurementAnalyzer:
    def __init__(self, rule_path: str | Path | None = None) -> None:
        self.rule_path = Path(rule_path) if rule_path else Path(__file__).parents[1] / "rules" / "measurement_rules.yaml"
        self.rules = self._load_rules()

    def analyze(self, measurement: MeasurementInput) -> MeasurementAnalysisResult:
        latest_history = self._latest_history(measurement)
        if latest_history is None:
            recommendation = self._recommendation(measurement.confidence)
            report = f"个体 {measurement.animal_id} 当前体尺已记录。无历史记录，不能判断增长趋势。{recommendation}"
            return MeasurementAnalysisResult(
                animal_id=measurement.animal_id,
                summary="无历史记录，仅描述当前体尺值，不能判断增长趋势。",
                abnormal_items=[],
                evidence=[],
                recommendation=recommendation,
                report=report,
                used_demo_history=measurement.use_demo_history,
            )

        abnormal_items: list[str] = []
        evidence: list[str] = []
        current_values = measurement.current.model_dump()
        history_values = latest_history.model_dump()
        thresholds = self.rules["slow_growth_thresholds"]

        for field, threshold in thresholds.items():
            current_value = current_values.get(field)
            history_value = history_values.get(field)
            if current_value is None or history_value is None:
                continue
            delta = round(float(current_value) - float(history_value), 1)
            if delta < float(threshold):
                abnormal_items.append(field)
                evidence.append(self._format_evidence(field, history_value, current_value, delta))

        if abnormal_items:
            summary = "发现部分体尺指标增长偏慢，异常结论已附数值依据。"
        else:
            summary = "当前体尺与最近历史记录相比未触发异常阈值。"

        recommendation = self._recommendation(measurement.confidence)
        report_parts = [
            f"个体 {measurement.animal_id} 体尺分析：{summary}",
            *evidence,
            recommendation,
        ]
        if measurement.use_demo_history:
            report_parts.insert(0, "数据说明：以下历史记录为演示数据，仅用于功能展示，不代表真实个体体尺记录。")

        return MeasurementAnalysisResult(
            animal_id=measurement.animal_id,
            summary=summary,
            abnormal_items=abnormal_items,
            evidence=evidence,
            recommendation=recommendation,
            report="\n".join(report_parts),
            used_demo_history=measurement.use_demo_history,
        )

    def _latest_history(self, measurement: MeasurementInput):
        if not measurement.history:
            return None
        return max(measurement.history, key=lambda item: item.measure_date)

    def _format_evidence(
        self,
        field: str,
        history_value: float,
        current_value: float,
        delta: float,
    ) -> str:
        label = self.rules["field_labels"].get(field, field)
        unit = self.rules["units"].get(field, "")
        return f"{label}从 {history_value:.1f} {unit} 增至 {current_value:.1f} {unit}，增长 {delta:.1f} {unit}"

    def _recommendation(self, confidence: float | None) -> str:
        if confidence is not None and confidence < 0.6:
            return "测量置信度偏低，建议复测后再判断。"
        return "建议结合采食量、体重变化、年龄和饲养环境进一步判断。"

    def _load_rules(self) -> dict[str, Any]:
        with self.rule_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return {
            "slow_growth_thresholds": data.get("slow_growth_thresholds", {}),
            "field_labels": data.get("field_labels", {}),
            "units": data.get("units", {}),
        }
