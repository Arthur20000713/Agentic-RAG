from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("0", "A", "B", "C", "D", "E", "F", "G", "H", "full")


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
    if stage in {"D", "full"}:
        failures.extend(_check_stage_d())
    if stage in {"E", "full"}:
        failures.extend(_check_stage_e())
    if stage in {"F", "full"}:
        failures.extend(_check_stage_f())
    if stage in {"G", "full"}:
        failures.extend(_check_stage_g())
    if stage in {"H", "full"}:
        failures.extend(_check_stage_h())
    if stage in {"full"}:
        failures.extend(_check_future_stage_declared(stage))
    return failures


def _check_baseline() -> list[str]:
    required_files = [
        "docs/DEV_SPEC_v3.md",
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

    dev_spec = _read_text("docs/DEV_SPEC_v3.md")
    for required_text in ("V3.0-A1", "V3.0-A2", "V3.0-A3", "进度跟踪"):
        if required_text not in dev_spec:
            failures.append(f"docs/DEV_SPEC_v3.md is missing required V3 text: {required_text}")

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
            "backend/app/model/router_policy.py",
            "backend/app/agent/graph.py",
            "backend/app/agent/langgraph_workflow.py",
            "backend/app/db/migrations.py",
            "backend/app/db/repositories.py",
            "tests/unit/test_safety_precheck.py",
            "tests/unit/test_model_router.py",
            "tests/integration/test_agent_graph.py",
            "tests/integration/test_model_route_log.py",
        ]
    )
    precheck = _read_text("backend/app/agent/safety_precheck.py")
    router = _read_text("backend/app/model/router.py")
    router_policy = _read_text("backend/app/model/router_policy.py")
    graph = _read_text("backend/app/agent/langgraph_workflow.py")
    migrations = _read_text("backend/app/db/migrations.py")
    repositories = _read_text("backend/app/db/repositories.py")
    tests = _read_text("tests/unit/test_safety_precheck.py")
    router_tests = _read_text("tests/unit/test_model_router.py")
    graph_tests = _read_text("tests/integration/test_agent_graph.py")
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
    ):
        if required_text not in router:
            failures.append(f"model/router.py is missing required text: {required_text}")
        if required_text not in router_tests:
            failures.append(f"test_model_router.py is missing required coverage text: {required_text}")
    for required_text in (
        "high_risk_requires_primary",
        "risk_final_answer_requires_primary",
    ):
        if required_text not in router_policy:
            failures.append(f"model/router_policy.py is missing required text: {required_text}")
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
    for required_text in ("_record_model_router_shadow", "model_router_shadow", "ModelRouter", "SafetyPrecheck"):
        if required_text not in graph:
            failures.append(f"graph.py is missing required shadow route text: {required_text}")
    for required_text in ("model_router_shadow", "shadow_model", "local_small"):
        if required_text not in graph_tests:
            failures.append(f"test_agent_graph.py is missing required shadow route coverage text: {required_text}")
    return failures


def _check_stage_d() -> list[str]:
    failures = _missing_paths(
        [
            "backend/app/model/base.py",
            "backend/app/model/local_client.py",
            "backend/app/model/query_normalizer.py",
            "backend/app/agent/disease_agent.py",
            "backend/app/agent/measurement_agent.py",
            "tests/unit/test_local_model_client.py",
            "tests/unit/test_query_normalizer.py",
            "tests/unit/test_disease_agent.py",
            "tests/unit/test_measurement_agent.py",
            "tests/e2e/test_measurement_report_flow.py",
        ]
    )
    base = _read_text("backend/app/model/base.py")
    local_client = _read_text("backend/app/model/local_client.py")
    query_normalizer = _read_text("backend/app/model/query_normalizer.py")
    disease_agent = _read_text("backend/app/agent/disease_agent.py")
    measurement_agent = _read_text("backend/app/agent/measurement_agent.py")
    tests = _read_text("tests/unit/test_local_model_client.py")
    normalizer_tests = _read_text("tests/unit/test_query_normalizer.py")
    disease_tests = _read_text("tests/unit/test_disease_agent.py")
    measurement_tests = _read_text("tests/unit/test_measurement_agent.py")
    measurement_e2e_tests = _read_text("tests/e2e/test_measurement_report_flow.py")
    for required_text in ("BaseModelClient", "generate_json"):
        if required_text not in base:
            failures.append(f"model/base.py is missing required local model text: {required_text}")
    for required_text in ("LocalModelClient", "BaseModelClient", "generate_json", "final_answer", "fallback_required"):
        if required_text not in local_client:
            failures.append(f"local_client.py is missing required text: {required_text}")
        if required_text not in tests:
            failures.append(f"test_local_model_client.py is missing required coverage text: {required_text}")
    for required_text in (
        "normalize_query",
        "QueryNormalizationResult",
        "QueryNormalizationPayload",
        "schema_validation_failed",
        "model_requested_fallback",
    ):
        if required_text not in query_normalizer:
            failures.append(f"query_normalizer.py is missing required text: {required_text}")
        if required_text not in normalizer_tests:
            failures.append(f"test_query_normalizer.py is missing required coverage text: {required_text}")
    for removed_text in ("extract_slots_with_router", "disease_slot_router", "slot_extractor"):
        if removed_text in disease_agent:
            failures.append(f"disease_agent.py still contains removed slot extraction text: {removed_text}")
    for required_text in ("rag_ready", "without_fixed_slot_follow_up", "does_not_block_rag_query"):
        if required_text not in disease_tests:
            failures.append(f"test_disease_agent.py is missing dynamic disease RAG coverage text: {required_text}")
    for required_text in ("render_measurement_json", "measurement_json_renderer", "ModelRouter", "report_json"):
        if required_text not in measurement_agent:
            failures.append(f"measurement_agent.py is missing required JSON renderer text: {required_text}")
    for required_text in ("measurement_json_renderer", "local_small", "abnormal_items"):
        if required_text not in measurement_tests:
            failures.append(f"test_measurement_agent.py is missing required JSON renderer coverage text: {required_text}")
        if required_text not in measurement_e2e_tests:
            failures.append(f"test_measurement_report_flow.py is missing required JSON renderer coverage text: {required_text}")
    return failures


def _check_stage_e() -> list[str]:
    failures = _missing_paths(
        [
            "backend/app/agent/verifier_agent.py",
            "backend/app/agent/safety_agent.py",
            "backend/app/rules/safety_rules.yaml",
            "backend/app/evaluation/v3_safety_runner.py",
            "tests/fixtures/v3_safety_redteam.json",
            "tests/unit/test_verifier_agent.py",
            "tests/unit/test_safety_agent.py",
            "tests/integration/test_v3_safety_runner.py",
        ]
    )
    verifier = _read_text("backend/app/agent/verifier_agent.py")
    safety_agent = _read_text("backend/app/agent/safety_agent.py")
    safety_rules = _read_text("backend/app/rules/safety_rules.yaml")
    safety_runner = _read_text("backend/app/evaluation/v3_safety_runner.py")
    safety_fixture = _read_text("tests/fixtures/v3_safety_redteam.json")
    tests = _read_text("tests/unit/test_verifier_agent.py")
    safety_tests = _read_text("tests/unit/test_safety_agent.py")
    safety_runner_tests = _read_text("tests/integration/test_v3_safety_runner.py")
    for required_text in ("ClaimCheck", "claim_checks", "source_uri", "claim_missing_source_uri"):
        if required_text not in verifier:
            failures.append(f"verifier_agent.py is missing required claim check text: {required_text}")
    for required_text in ("claim_checks", "source_uri", "claim_missing_source_uri"):
        if required_text not in tests:
            failures.append(f"test_verifier_agent.py is missing required claim check coverage text: {required_text}")
    for required_text in ("S4_HARD_VIOLATIONS", "hard_blocked", "hard_violations"):
        if required_text not in safety_agent:
            failures.append(f"safety_agent.py is missing required hard block text: {required_text}")
    for required_text in ("dosage", "prescription", "definitive_diagnosis"):
        if required_text not in safety_rules:
            failures.append(f"safety_rules.yaml is missing required hard block rule: {required_text}")
        if required_text not in safety_tests:
            failures.append(f"test_safety_agent.py is missing required hard block coverage text: {required_text}")
        if required_text not in safety_fixture:
            failures.append(f"v3_safety_redteam.json is missing required hard block fixture text: {required_text}")
    for required_text in ("V3SafetyEvalRunner", "safety_pass_rate", "v3_safety_result.json", "V3SafetyEvaluationReport"):
        if required_text not in safety_runner:
            failures.append(f"v3_safety_runner.py is missing required red-team eval text: {required_text}")
    for required_text in ("V3SafetyEvalRunner", "safety_pass_rate", "v3_safety_result.json"):
        if required_text not in safety_runner_tests:
            failures.append(f"test_v3_safety_runner.py is missing required red-team eval coverage text: {required_text}")
    return failures


def _check_stage_f() -> list[str]:
    failures = _missing_paths(
        [
            "backend/app/lora/dataset.py",
            "backend/app/lora/registry.py",
            "scripts/export_lora_dataset.py",
            "tests/unit/test_lora_dataset.py",
            "tests/unit/test_lora_registry.py",
            "tests/integration/test_lora_export.py",
        ]
    )
    dataset = _read_text("backend/app/lora/dataset.py")
    registry = _read_text("backend/app/lora/registry.py")
    exporter = _read_text("scripts/export_lora_dataset.py")
    tests = _read_text("tests/unit/test_lora_dataset.py")
    registry_tests = _read_text("tests/unit/test_lora_registry.py")
    export_tests = _read_text("tests/integration/test_lora_export.py")
    for required_text in (
        "LoraTrainingExample",
        "FORBIDDEN_FIELD_NAMES",
        "raw_rag_text",
        "api_key",
        "extra=\"forbid\"",
    ):
        if required_text not in dataset:
            failures.append(f"lora/dataset.py is missing required dataset schema text: {required_text}")
    for required_text in ("LoraTrainingExample", "raw_rag_text", "api_key", "required"):
        if required_text not in tests:
            failures.append(f"test_lora_dataset.py is missing required dataset coverage text: {required_text}")
    for required_text in ("export_lora_dataset", "ALLOWED_EXAMPLE_FIELDS", "max_text_chars", "FORBIDDEN_FIELD_NAMES"):
        if required_text not in exporter:
            failures.append(f"export_lora_dataset.py is missing required export text: {required_text}")
    for required_text in ("export_lora_dataset", "raw_rag_text", "api_key", "rag_context", "truncates"):
        if required_text not in export_tests:
            failures.append(f"test_lora_export.py is missing required export coverage text: {required_text}")
    for required_text in ("ModelRegistry", "ModelRegistryEntry", "enabled_for_inference", "active_inference_models"):
        if required_text not in registry:
            failures.append(f"lora/registry.py is missing required registry text: {required_text}")
        if required_text not in registry_tests:
            failures.append(f"test_lora_registry.py is missing required registry coverage text: {required_text}")
    return failures


def _check_stage_g() -> list[str]:
    failures = _missing_paths(
        [
            "backend/app/db/migrations.py",
            "backend/app/db/repositories.py",
            "backend/app/services/memory_service.py",
            "backend/app/agent/graph.py",
            "backend/app/agent/langgraph_workflow.py",
            "backend/app/api/measurement.py",
            "tests/integration/test_memory_schema.py",
            "tests/integration/test_memory_repository.py",
            "tests/e2e/test_memory_flow.py",
            "tests/unit/test_memory_service.py",
        ]
    )
    migrations = _read_text("backend/app/db/migrations.py")
    repositories = _read_text("backend/app/db/repositories.py")
    service = _read_text("backend/app/services/memory_service.py")
    graph = _read_text("backend/app/agent/langgraph_workflow.py")
    measurement_api = _read_text("backend/app/api/measurement.py")
    tests = _read_text("tests/integration/test_memory_schema.py")
    repository_tests = _read_text("tests/integration/test_memory_repository.py")
    memory_flow_tests = _read_text("tests/e2e/test_memory_flow.py")
    service_tests = _read_text("tests/unit/test_memory_service.py")
    for required_text in ("memory_event", "payload_json", "supersedes_event_id", "farm_memory", "animal_memory"):
        if required_text not in migrations:
            failures.append(f"migrations.py is missing required memory event text: {required_text}")
        if required_text not in tests:
            failures.append(f"test_memory_schema.py is missing required memory schema coverage text: {required_text}")
    for required_text in ("MemoryRepository", "supersede_fact", "delete_fact", "get_projection"):
        if required_text not in repositories:
            failures.append(f"repositories.py is missing required memory repository text: {required_text}")
        if required_text not in repository_tests:
            failures.append(f"test_memory_repository.py is missing required memory repository coverage text: {required_text}")
    for required_text in ("MemoryService", "MemoryFact", "maybe_write_memory", "user_confirmed", "tool_result", "ai_inferred"):
        if required_text not in service:
            failures.append(f"memory_service.py is missing required memory service text: {required_text}")
        if required_text not in service_tests:
            failures.append(f"test_memory_service.py is missing required memory service coverage text: {required_text}")
    for required_text in ("maybe_write_memory", "build_measurement_memory_fact", "user_confirmed_observation"):
        if required_text not in graph:
            failures.append(f"graph.py is missing required memory write text: {required_text}")
    for required_text in ("MemoryRepository", "memory_write_enabled", "MemoryService", "run_measurement_graph"):
        if required_text not in measurement_api:
            failures.append(f"measurement.py is missing required memory API text: {required_text}")
    for required_text in ("maybe_write_memory", "abnormal_items", "risk_level", "diagnosis"):
        if required_text not in memory_flow_tests:
            failures.append(f"test_memory_flow.py is missing required memory E2E coverage text: {required_text}")
    return failures


def _check_stage_h() -> list[str]:
    failures = _missing_paths(
        [
            "backend/app/evaluation/v3_runner.py",
            "backend/app/evaluation/v3_report.py",
            "backend/app/evaluation/real_rag_runner.py",
            "backend/app/api/traces.py",
            "backend/app/static/frontend/app.js",
            "scripts/run_eval.py",
            "tests/integration/test_eval_runner.py",
            "tests/integration/test_v3_report.py",
            "tests/integration/test_trace_api.py",
            "tests/integration/test_frontend_contract.py",
        ]
    )
    v3_runner = _read_text("backend/app/evaluation/v3_runner.py")
    v3_report = _read_text("backend/app/evaluation/v3_report.py")
    real_rag_runner = _read_text("backend/app/evaluation/real_rag_runner.py")
    traces_api = _read_text("backend/app/api/traces.py")
    frontend_js = _read_text("backend/app/static/frontend/app.js")
    run_eval = _read_text("scripts/run_eval.py")
    eval_tests = _read_text("tests/integration/test_eval_runner.py")
    report_tests = _read_text("tests/integration/test_v3_report.py")
    trace_tests = _read_text("tests/integration/test_trace_api.py")
    frontend_tests = _read_text("tests/integration/test_frontend_contract.py")
    for required_text in (
        "V3EvalRunner",
        "v2_baseline",
        "v3_off",
        "router_shadow",
        "router_low_risk",
        "V3 Evaluation Summary",
    ):
        if required_text not in v3_runner:
            failures.append(f"v3_runner.py is missing required V3 eval text: {required_text}")
        if required_text not in eval_tests:
            failures.append(f"test_eval_runner.py is missing required V3 eval coverage text: {required_text}")
    for required_text in ('"v3"', "V3EvalRunner", "args.mode == \"v3\""):
        if required_text not in run_eval:
            failures.append(f"run_eval.py is missing required V3 mode text: {required_text}")
    for required_text in ("build_v3_report", "route", "safety", "memory", "fallback", "to_markdown"):
        if required_text not in v3_report:
            failures.append(f"v3_report.py is missing required V3 report text: {required_text}")
        if required_text not in report_tests:
            failures.append(f"test_v3_report.py is missing required V3 report coverage text: {required_text}")
    for required_text in ("v3_report.json", "v3_report.md", "build_v3_report"):
        if required_text not in v3_runner:
            failures.append(f"v3_runner.py is missing required V3 report output text: {required_text}")
    for required_text in ("v3_debug_summary", "flags", "route", "safety", "memory"):
        if required_text not in traces_api:
            failures.append(f"traces.py is missing required V3 debug API text: {required_text}")
        if required_text not in trace_tests:
            failures.append(f"test_trace_api.py is missing required V3 debug API coverage text: {required_text}")
        if required_text not in frontend_js:
            failures.append(f"app.js is missing required V3 debug frontend text: {required_text}")
        if required_text not in frontend_tests:
            failures.append(f"test_frontend_contract.py is missing required V3 debug frontend coverage text: {required_text}")
    for required_text in ('"mode": "real"', "Real RAG Evaluation Summary"):
        if required_text not in real_rag_runner:
            failures.append(f"real_rag_runner.py is missing required real RAG report text: {required_text}")
    for required_text in ("test_real_rag_runner_writes_real_mode_report", 'payload["mode"] == "real"'):
        if required_text not in eval_tests:
            failures.append(f"test_eval_runner.py is missing required real RAG report coverage text: {required_text}")
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
    dev_spec = _read_text("docs/DEV_SPEC_v3.md")
    headings = [stage_headings[key] for key in ("B", "C", "D", "E", "F", "G", "full")] if stage == "full" else [stage_headings[stage]]
    return [
        f"docs/DEV_SPEC_v3.md is missing future stage declaration: {heading}"
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
