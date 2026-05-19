from __future__ import annotations

import json
from pathlib import Path

from backend.app.evaluation.v5_runner import compute_v5_safety_metrics, run_v5_safety_case


def test_v5_safety_fixture_blocks_high_risk_takeover() -> None:
    cases = json.loads(Path("tests/fixtures/v5_safety_redteam.json").read_text(encoding="utf-8"))

    results = [run_v5_safety_case(case) for case in cases]
    metrics = compute_v5_safety_metrics(results)

    assert metrics["total_cases"] == len(cases)
    assert metrics["safety_redteam_pass_rate"] == 1.0
    assert metrics["high_risk_blocked_count"] == len(cases)
    assert all(result["selected_model"] == "primary" for result in results)
    assert all(result["blocked_reason"] == "high_risk_requires_primary" for result in results)
