from __future__ import annotations

from backend.app.agent.safety import FinalSafetyGuard, SafetyGuard


def test_safety_blocks_specific_dosage() -> None:
    result = SafetyGuard().check("建议注射青霉素 10 ml，每天一次。")

    assert result.passed is False
    assert "dosage" in result.violations


def test_safety_blocks_definitive_diagnosis() -> None:
    result = SafetyGuard().check("可以确定诊断为牛瘟。")

    assert result.passed is False
    assert "definitive_diagnosis" in result.violations


def test_final_safety_guard_rewrites_unsafe_answer() -> None:
    answer = FinalSafetyGuard().enforce("确诊为肺炎，使用药物 5 mg/kg。")

    assert "5 mg/kg" not in answer
    assert "不能提供具体药物剂量" in answer
    assert "兽医" in answer


def test_safety_blocks_fabricated_tool_result_claim() -> None:
    result = SafetyGuard().check("虽然工具调用失败，但检索结果显示应立即用药。")

    assert result.passed is False
    assert "fabricated_tool_result" in result.violations

