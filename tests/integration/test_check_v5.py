from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from scripts.check_v5 import check_local_model_config


def _tmp_root() -> Path:
    root = Path(".tmp_tests") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_check_local_model_config_accepts_default_mock_config() -> None:
    root = _tmp_root()
    _write(root / "DEV_SPEC_V5.md", "# V5\n")
    _write(root / "docs" / "V5_LOCAL_MODEL_GUIDE.md", "# guide\n")
    _write(root / "backend" / "app" / "model" / "local_backends.py", "# local backends\n")
    _write(root / "backend" / "app" / "model" / "local_schema.py", "# local schema\n")
    _write(root / "scripts" / "run_local_model_smoke.py", "# smoke\n")
    _write(
        root / "config" / "settings.yaml",
        """
local_model:
  enabled: false
  provider: mock
  endpoint:
  model:
  timeout_seconds: 3
  max_retries: 0
  allow_final_answer: false
""",
    )

    assert check_local_model_config(root) == []


def test_check_local_model_config_reports_missing_v5_fields() -> None:
    root = _tmp_root()
    _write(root / "DEV_SPEC_V5.md", "# V5\n")
    _write(root / "docs" / "V5_LOCAL_MODEL_GUIDE.md", "# guide\n")
    _write(root / "backend" / "app" / "model" / "local_backends.py", "# local backends\n")
    _write(root / "backend" / "app" / "model" / "local_schema.py", "# local schema\n")
    _write(root / "scripts" / "run_local_model_smoke.py", "# smoke\n")
    _write(root / "config" / "settings.yaml", "local_model:\n  provider: mock\n")

    failures = check_local_model_config(root)

    assert "config/settings.yaml: local_model.endpoint must be present for V5" in failures
    assert "config/settings.yaml: local_model.allow_final_answer must be present for V5" in failures


def test_check_v5_full_cli_passes_without_real_local_model() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/check_v5.py", "--stage", "full"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V5 checks passed for stage full" in completed.stdout
    assert "Ollama" not in completed.stderr


def test_check_v5_local_model_cli_runs_optional_smoke() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/check_v5.py", "--stage", "local-model"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "V5 checks passed for stage local-model" in completed.stdout
    assert "SKIPPED: real local model is not configured" in completed.stdout
