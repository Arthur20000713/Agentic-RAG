from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("0", "A", "B", "C", "D", "E", "F", "G", "full")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight V3 contract checks.")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="0",
        help="V3 check stage. Stage 0 is the baseline repo/harness check and never starts real RAG.",
    )
    args = parser.parse_args(argv)

    failures = _check_stage(args.stage)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"V3 checks passed for stage {args.stage}")
    return 0


def _check_stage(stage: str) -> list[str]:
    failures = _check_baseline()
    if stage in {"A", "full"}:
        failures.extend(_check_stage_a())
    if stage in {"B", "C", "D", "E", "F", "G", "full"}:
        failures.extend(_check_future_stage_declared(stage))
    return failures


def _check_baseline() -> list[str]:
    required_files = [
        "DEV_SPEC_v3.md",
        "docs/V3_REPO_MAP.md",
        "backend/app/main.py",
        "backend/app/agent/graph.py",
        "backend/app/integrations/rag_server/base.py",
        "backend/app/evaluation/multi_agent_runner.py",
        "config/settings.yaml",
        "config/settings.test.yaml",
        "scripts/run_eval.py",
        "scripts/check_v2.py",
        "tests",
    ]
    failures = _missing_paths(required_files)

    if (ROOT / "backend" / "tests").exists():
        failures.append("V3 must use tests/, not backend/tests/")
    if (ROOT / "configs").exists():
        failures.append("V3 must use config/, not configs/")

    repo_map = _read_text("docs/V3_REPO_MAP.md")
    for required_text in (
        "APP_ROOT",
        "backend/app",
        "TEST_ROOT",
        "tests",
        "CONFIG_ROOT",
        "config",
        "RAG_SERVER_PATH",
        "RAG-SERVER",
    ):
        if required_text not in repo_map:
            failures.append(f"docs/V3_REPO_MAP.md is missing required text: {required_text}")

    dev_spec = _read_text("DEV_SPEC_v3.md")
    for required_text in ("V3.0-A1", "V3.0-A2", "V3.0-A3", "进度跟踪"):
        if required_text not in dev_spec:
            failures.append(f"DEV_SPEC_v3.md is missing required V3 text: {required_text}")

    return failures


def _check_stage_a() -> list[str]:
    failures = _missing_paths(
        [
            "scripts/check_v3.py",
            "tests/integration/test_cli_scripts.py",
            "backend/app/core/config.py",
            "config/settings.yaml",
            "config/settings.test.yaml",
        ]
    )
    settings = _read_text("config/settings.yaml")
    test_settings = _read_text("config/settings.test.yaml")
    config_py = _read_text("backend/app/core/config.py")
    for required_text in (
        "v3:",
        "model_router:",
        "local_model:",
        "lora:",
        "long_term_memory:",
        "enhanced_safety:",
    ):
        if required_text not in settings:
            failures.append(f"config/settings.yaml is missing V3 config block: {required_text}")
        if required_text not in test_settings:
            failures.append(f"config/settings.test.yaml is missing V3 config block: {required_text}")
    for class_name in (
        "V3Settings",
        "ModelRouterSettings",
        "LocalModelSettings",
        "LoraSettings",
        "LongTermMemorySettings",
        "EnhancedSafetySettings",
    ):
        if class_name not in config_py:
            failures.append(f"backend/app/core/config.py is missing {class_name}")
    return failures


def _check_future_stage_declared(stage: str) -> list[str]:
    stage_headings = {
        "B": "V3.1",
        "C": "V3.2",
        "D": "V3.3",
        "E": "V3.4",
        "F": "V3.5",
        "G": "V3.6",
        "full": "V3.7",
    }
    dev_spec = _read_text("DEV_SPEC_v3.md")
    headings = [stage_headings[key] for key in ("B", "C", "D", "E", "F", "G", "full")] if stage == "full" else [stage_headings[stage]]
    return [
        f"DEV_SPEC_v3.md is missing future stage declaration: {heading}"
        for heading in headings
        if heading not in dev_spec
    ]


def _missing_paths(paths: list[str]) -> list[str]:
    return [f"missing required path: {path}" for path in paths if not (ROOT / path).exists()]


def _read_text(path: str) -> str:
    candidate = ROOT / path
    if not candidate.exists():
        return ""
    return candidate.read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
