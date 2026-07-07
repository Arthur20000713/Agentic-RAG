from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_check_v6_baseline_cli_passes_for_current_repo() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v6.py",
            "--stage",
            "baseline",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V6 checks passed for stage baseline" in completed.stdout


def test_check_v6_runtime_cli_passes_for_current_repo() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/check_v6.py",
            "--stage",
            "runtime",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V6 checks passed for stage runtime" in completed.stdout


def test_check_v6_runtime_stage_tracks_health_endpoints() -> None:
    text = Path("scripts/check_v6.py").read_text(encoding="utf-8")

    assert "backend/app/api/health.py" in text
    assert "/api/health" in text
    assert "/api/ready" in text


def test_check_v6_full_stage_tracks_answer_quality_guard() -> None:
    text = Path("scripts/check_v6.py").read_text(encoding="utf-8")

    assert "backend/app/model/answer_generator.py" in text
    assert "Query Results" in text
    assert "source_uri" in text


def test_check_v6_baseline_tracks_v3_shadow_defaults() -> None:
    text = Path("scripts/check_v6.py").read_text(encoding="utf-8")

    assert "v3.enabled must be true" in text
    assert "model_router.shadow_mode must be true" in text
    assert "local_model.allow_final_answer must remain false" in text
