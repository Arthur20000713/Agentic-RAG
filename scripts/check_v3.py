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
    if stage in {"B", "full"}:
        failures.extend(_check_stage_b())
    if stage in {"C", "full"}:
        failures.extend(_check_stage_c())
    if stage in {"D", "E", "F", "G", "full"}:
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


def _check_stage_b() -> list[str]:
    failures = _missing_paths(
        [
            "backend/app/services/feature_flag_service.py",
            "backend/app/services/chat_service.py",
            "tests/unit/test_feature_flags.py",
            "tests/e2e/test_v3_disabled_regression.py",
        ]
    )
    service = _read_text("backend/app/services/feature_flag_service.py")
    chat_service = _read_text("backend/app/services/chat_service.py")
    tests = _read_text("tests/unit/test_feature_flags.py")
    api_tests = _read_text("tests/integration/test_api_contract.py")
    disabled_e2e_tests = _read_text("tests/e2e/test_v3_disabled_regression.py")
    for required_text in (
        "FeatureFlagService",
        "FeatureFlagSnapshot",
        "model_router_low_risk_takeover_enabled",
        "safety_precheck_enabled",
    ):
        if required_text not in service:
            failures.append(f"feature_flag_service.py is missing required text: {required_text}")
    for required_text in ("build_debug_payload", "v3_debug", "FeatureFlagService"):
        if required_text not in chat_service:
            failures.append(f"chat_service.py is missing V3 debug payload text: {required_text}")
    for required_text in ("v3_enabled", "model_router", "long_term_memory", "lora"):
        if required_text not in tests:
            failures.append(f"test_feature_flags.py is missing required coverage text: {required_text}")
    if "v3_debug" not in api_tests:
        failures.append("test_api_contract.py must cover v3_debug")
    for required_text in (
        "v3_disabled",
        "/api/chat",
        "/api/measurement/analyze",
        "model_router",
        "long_term_memory",
    ):
        if required_text not in disabled_e2e_tests:
            failures.append(f"test_v3_disabled_regression.py is missing required coverage text: {required_text}")
    return failures


def _check_stage_c() -> list[str]:
    failures = _missing_paths(
        [
            "backend/app/agent/safety_precheck.py",
            "backend/app/model/router.py",
            "backend/app/db/migrations.py",
            "backend/app/db/repositories.py",
            "tests/unit/test_safety_precheck.py",
            "tests/unit/test_model_router.py",
            "tests/integration/test_model_route_log.py",
        ]
    )
    precheck = _read_text("backend/app/agent/safety_precheck.py")
    router = _read_text("backend/app/model/router.py")
    migrations = _read_text("backend/app/db/migrations.py")
    repositories = _read_text("backend/app/db/repositories.py")
    tests = _read_text("tests/unit/test_safety_precheck.py")
    router_tests = _read_text("tests/unit/test_model_router.py")
    route_log_tests = _read_text("tests/integration/test_model_route_log.py")
    for required_text in (
        "SafetyPrecheck",
        "SafetyPrecheckResult",
        "classify",
        "S0",
        "S1",
        "S2",
        "S3",
        "S4",
        "dosage",
        "prescription",
        "group_outbreak",
        "food_safety",
    ):
        if required_text not in precheck:
            failures.append(f"safety_precheck.py is missing required text: {required_text}")
    for required_text in (
        "SafetyPrecheck",
        "classify",
        "S0",
        "S1",
        "S2",
        "S3",
        "S4",
        "dosage",
        "prescription",
        "group_outbreak",
        "food_safety",
    ):
        if required_text not in tests:
            failures.append(f"test_safety_precheck.py is missing required coverage text: {required_text}")
    for required_text in (
        "ModelRouter",
        "ModelRouteRequest",
        "ModelRouteDecision",
        "local_small",
        "high_risk_requires_primary",
        "risk_final_answer_requires_primary",
    ):
        if required_text not in router:
            failures.append(f"model/router.py is missing required text: {required_text}")
        if required_text not in router_tests:
            failures.append(f"test_model_router.py is missing required coverage text: {required_text}")
    if "model_route_log" not in migrations:
        failures.append("migrations.py is missing model_route_log")
    for required_text in ("ModelRouteLogRepository", "route_request_json", "route_decision_json", "list_by_request_id"):
        if required_text not in repositories:
            failures.append(f"repositories.py is missing required model route log text: {required_text}")
    for required_text in ("ModelRouteLogRepository", "route_mode", "shadow", "list_by_request_id"):
        if required_text not in route_log_tests:
            failures.append(f"test_model_route_log.py is missing required coverage text: {required_text}")
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
