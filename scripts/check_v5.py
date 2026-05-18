from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("local-model", "full")
REQUIRED_LOCAL_MODEL_FILES = (
    "DEV_SPEC_V5.md",
    "docs/V5_LOCAL_MODEL_GUIDE.md",
    "backend/app/model/local_backends.py",
    "backend/app/model/local_schema.py",
    "scripts/run_local_model_smoke.py",
)
REQUIRED_LOCAL_MODEL_FIELDS = (
    "enabled",
    "provider",
    "endpoint",
    "model",
    "timeout_seconds",
    "max_retries",
    "allow_final_answer",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight V5 contract checks.")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="full",
        help="V5 check stage. full is static and never requires a real local model.",
    )
    args = parser.parse_args(argv)

    failures = check_local_model_config(ROOT)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    if args.stage == "local-model":
        tests_code = _run_pytest(
            [
                "tests/unit/test_config.py",
                "tests/unit/test_local_model_backend.py",
                "tests/unit/test_local_model_client.py",
            ]
        )
        if tests_code != 0:
            return tests_code
        smoke_code = run_local_model_optional_smoke(ROOT / ".tmp_tests" / "v5_local_model_smoke.json")
        if smoke_code != 0:
            return smoke_code

    print(f"V5 checks passed for stage {args.stage}")
    return 0


def check_local_model_config(root: Path) -> list[str]:
    failures = _missing_paths(root, REQUIRED_LOCAL_MODEL_FILES)
    config_path = root / "config" / "settings.yaml"
    if not config_path.exists():
        failures.append("missing required file: config/settings.yaml")
        return failures

    try:
        raw = _read_yaml(config_path)
    except (OSError, ValueError) as exc:
        failures.append(f"config/settings.yaml: {exc}")
        return failures

    local_model = raw.get("local_model")
    if not isinstance(local_model, dict):
        failures.append("config/settings.yaml: local_model must be a mapping")
        return failures

    for field in REQUIRED_LOCAL_MODEL_FIELDS:
        if field not in local_model:
            failures.append(f"config/settings.yaml: local_model.{field} must be present for V5")

    if local_model.get("provider") == "mock" and local_model.get("enabled") is not False:
        failures.append("config/settings.yaml: mock local_model must remain disabled by default")
    if local_model.get("allow_final_answer") is not False:
        failures.append("config/settings.yaml: local_model.allow_final_answer must default to false")
    return failures


def run_local_model_optional_smoke(output: Path) -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_local_model_smoke.py",
            "--optional",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    return completed.returncode


def _run_pytest(paths: list[str]) -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    return completed.returncode


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("settings file must contain a mapping")
    return data


def _missing_paths(root: Path, paths: tuple[str, ...]) -> list[str]:
    return [f"missing required file: {path}" for path in paths if not (root / path).exists()]


if __name__ == "__main__":
    raise SystemExit(main())
