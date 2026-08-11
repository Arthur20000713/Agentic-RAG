from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("baseline", "runtime", "full")

REQUIRED_BASELINE_FILES = (
    "docs/DEV_SPEC_V6.md",
    "config/settings.yaml",
    "docs/rag_corpus/reports/batch_002_quality.md",
    "scripts/run_eval.py",
    "scripts/doctor_v6.py",
    "scripts/start_app.ps1",
    "scripts/check_v4_2.py",
    "scripts/check_v5.py",
)

REQUIRED_SPEC_MARKERS = (
    "V6.0-A0",
    "V6.0-A1",
    "V6.1-B",
    "V6.2-C",
    "V6.3-D",
    "V6.4-E",
    "V6.5-F",
    "V6.6-G",
    "commit and push",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run V6 productization checks.")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="baseline",
        help="V6 check stage. Baseline is static and does not start external services.",
    )
    args = parser.parse_args(argv)

    failures = check_baseline(ROOT)
    if args.stage in {"runtime", "full"}:
        failures.extend(check_runtime(ROOT))
    if args.stage == "full":
        failures.extend(check_answer_quality(ROOT))
        failures.extend(check_local_model_acceptance(ROOT))
        failures.extend(check_release_entrypoint(ROOT))
        failures.extend(_run_existing_check(["scripts/check_v4_2.py", "--stage", "full"]))
        failures.extend(_run_existing_check(["scripts/check_v5.py", "--stage", "full"]))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"V6 checks passed for stage {args.stage}")
    return 0


def check_baseline(root: Path) -> list[str]:
    failures: list[str] = []
    failures.extend(_missing_paths(root, REQUIRED_BASELINE_FILES))
    failures.extend(_check_dev_spec(root / "docs" / "DEV_SPEC_V6.md"))
    failures.extend(_check_default_real_rag(root / "config" / "settings.yaml"))
    failures.extend(_check_default_agent_runtime(root / "config" / "settings.yaml"))
    failures.extend(_check_disease_llm_takeover_config(root / "config" / "settings.yaml"))
    failures.extend(_check_batch_quality_report(root / "docs" / "rag_corpus" / "reports" / "batch_002_quality.md"))
    failures.extend(_check_run_eval_settings_arg(root / "scripts" / "run_eval.py"))
    return failures


def check_runtime(root: Path) -> list[str]:
    failures: list[str] = []
    doctor_script = root / "scripts" / "doctor_v6.py"
    start_script = root / "scripts" / "start_app.ps1"
    runtime_service = root / "backend" / "app" / "services" / "runtime_doctor.py"
    health_api = root / "backend" / "app" / "api" / "health.py"
    failures.extend(
        _missing_paths(
            root,
            (
                "scripts/doctor_v6.py",
                "scripts/start_app.ps1",
                "backend/app/services/runtime_doctor.py",
                "backend/app/api/health.py",
            ),
        )
    )
    if doctor_script.exists():
        text = doctor_script.read_text(encoding="utf-8")
        for marker in ("RuntimeDoctor", "--port", "--settings", "--json"):
            if marker not in text:
                failures.append(f"{doctor_script}: missing runtime doctor marker: {marker}")
    if start_script.exists():
        text = start_script.read_text(encoding="utf-8")
        for marker in ("doctor_v6.py", "uvicorn", "backend.app.main:app", "SkipDoctor"):
            if marker not in text:
                failures.append(f"{start_script}: missing startup marker: {marker}")
    if runtime_service.exists():
        text = runtime_service.read_text(encoding="utf-8")
        for marker in ("DEFAULT_REAL_RAG_NOT_CONFIGURED", "RAG_SERVER_PATH_INVALID", "RAG_SERVER_PYTHON_INVALID", "PORT_IN_USE"):
            if marker not in text:
                failures.append(f"{runtime_service}: missing diagnostic error marker: {marker}")
    if health_api.exists():
        text = health_api.read_text(encoding="utf-8")
        for marker in ("/api/health", "/api/ready", "RuntimeDoctor"):
            if marker not in text:
                failures.append(f"{health_api}: missing health endpoint marker: {marker}")
    failures.extend(_run_existing_check(["scripts/doctor_v6.py", "--json"]))
    return failures


def check_answer_quality(root: Path) -> list[str]:
    failures: list[str] = []
    answer_generator = root / "backend" / "app" / "model" / "answer_generator.py"
    answer_test = root / "tests" / "unit" / "test_answer_generator.py"
    workflow_test = root / "tests" / "integration" / "test_langgraph_workflow.py"
    failures.extend(
        _missing_paths(
            root,
            (
                "backend/app/model/answer_generator.py",
                "tests/unit/test_answer_generator.py",
                "tests/integration/test_langgraph_workflow.py",
            ),
        )
    )
    if answer_generator.exists():
        text = answer_generator.read_text(encoding="utf-8")
        lower_text = text.lower()
        for marker in ("_looks_like_retrieval_dump", "query results", "source_uri"):
            if marker not in lower_text:
                display = "Query Results" if marker == "query results" else marker
                failures.append(f"{answer_generator}: missing answer quality marker: {display}")
    if answer_test.exists():
        text = answer_test.read_text(encoding="utf-8")
        for marker in ("does_not_invent_citations", "Query Results", "source_uri"):
            if marker not in text:
                failures.append(f"{answer_test}: missing answer quality test marker: {marker}")
    if workflow_test.exists():
        text = workflow_test.read_text(encoding="utf-8")
        for marker in ("CountingRagClient", "Query Results", "evidence_status"):
            if marker not in text:
                failures.append(f"{workflow_test}: missing workflow answer quality test marker: {marker}")
    return failures


def check_local_model_acceptance(root: Path) -> list[str]:
    failures: list[str] = []
    config_path = root / "config" / "settings.yaml"
    report_path = root / "docs" / "local_model" / "transformers_smoke_report.json"
    failures.extend(
        _missing_paths(
            root,
            (
                "docs/local_model/transformers_smoke_report.json",
                "docs/V6_LOCAL_MODEL_ACCEPTANCE.md",
            ),
        )
    )
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            failures.append(f"{config_path}: invalid YAML: {exc}")
            raw = {}
        local_model = raw.get("local_model") if isinstance(raw, dict) and isinstance(raw.get("local_model"), dict) else {}
        if local_model.get("enabled") is not True:
            failures.append(f"{config_path}: local_model.enabled must be true for V6.5 transformers smoke")
        if local_model.get("provider") != "transformers":
            failures.append(f"{config_path}: local_model.provider must be transformers")
        if local_model.get("model") != "Qwen/Qwen2.5-0.5B-Instruct":
            failures.append(f"{config_path}: local_model.model must be Qwen/Qwen2.5-0.5B-Instruct")
        if local_model.get("allow_final_answer") is not False:
            failures.append(f"{config_path}: local_model.allow_final_answer must remain false")

    if report_path.exists():
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{report_path}: invalid JSON: {exc.msg}")
            payload = {}
        query_case = _find_case(payload, "query_normalization")
        if not isinstance(payload, dict) or payload.get("status") != "passed":
            failures.append(f"{report_path}: local model smoke report must pass")
        if not isinstance(payload, dict) or payload.get("provider") != "transformers":
            failures.append(f"{report_path}: local model smoke provider must be transformers")
        if query_case is None or query_case.get("status") != "passed" or query_case.get("fallback_required") is not False:
            failures.append(f"{report_path}: query_normalization smoke must pass without fallback")
    return failures


def check_release_entrypoint(root: Path) -> list[str]:
    failures = _missing_paths(root, ("scripts/check_release_v6.py", "docs/V6_RELEASE_CHECKLIST.md"))
    release_script = root / "scripts" / "check_release_v6.py"
    if release_script.exists():
        text = release_script.read_text(encoding="utf-8")
        for marker in ("release_check_summary.json", "V6 release status", "run_local_model_smoke.py"):
            if marker not in text:
                failures.append(f"{release_script}: missing release marker: {marker}")
    return failures


def _check_dev_spec(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [f"{path}: missing V6 marker: {marker}" for marker in REQUIRED_SPEC_MARKERS if marker not in text]


def _check_default_real_rag(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [f"{path}: invalid YAML: {exc}"]
    if not isinstance(raw, dict):
        return [f"{path}: settings must be a mapping"]
    rag_server = raw.get("rag_server")
    if not isinstance(rag_server, dict):
        return [f"{path}: missing rag_server mapping"]

    failures: list[str] = []
    expected_values: dict[str, Any] = {
        "query_mode": "real",
        "collection": "livestock_v4_2",
        "strict_real_mode": True,
    }
    for key, expected in expected_values.items():
        if rag_server.get(key) != expected:
            failures.append(f"{path}: rag_server.{key} must be {expected!r}")
    if not rag_server.get("repo_path"):
        failures.append(f"{path}: rag_server.repo_path must be configured for default real RAG")
    if not rag_server.get("python_executable"):
        failures.append(f"{path}: rag_server.python_executable must point to the RAG-SERVER Python")
    if float(rag_server.get("timeout_seconds") or 0) < 30:
        failures.append(f"{path}: rag_server.timeout_seconds must be at least 30 for default real RAG")
    return failures


def _check_default_agent_runtime(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [f"{path}: invalid YAML: {exc}"]
    if not isinstance(raw, dict):
        return [f"{path}: settings must be a mapping"]

    failures: list[str] = []
    agent_runtime = raw.get("agent_runtime") if isinstance(raw.get("agent_runtime"), dict) else {}
    model_router = raw.get("model_router") if isinstance(raw.get("model_router"), dict) else {}
    local_model = raw.get("local_model") if isinstance(raw.get("local_model"), dict) else {}
    if agent_runtime.get("engine") != "langgraph":
        failures.append(f"{path}: agent_runtime.engine must be langgraph")
    if model_router.get("enabled") is not True:
        failures.append(f"{path}: model_router.enabled must be true for the V6 default agent path")
    if model_router.get("shadow_mode") is not False:
        failures.append(f"{path}: model_router.shadow_mode must be false after local structured takeover acceptance")
    if model_router.get("allow_low_risk_takeover") is not True:
        failures.append(f"{path}: model_router.allow_low_risk_takeover must be true after local structured takeover acceptance")
    if local_model.get("allow_final_answer") is not False:
        failures.append(f"{path}: local_model.allow_final_answer must remain false")
    return failures


def _check_disease_llm_takeover_config(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [f"{path}: invalid YAML: {exc}"]
    if not isinstance(raw, dict):
        return [f"{path}: settings must be a mapping"]

    disease_llm = raw.get("disease_llm") if isinstance(raw.get("disease_llm"), dict) else {}
    primary_llm = raw.get("primary_llm") if isinstance(raw.get("primary_llm"), dict) else {}
    takeover_enabled = disease_llm.get("enabled") is True and disease_llm.get("shadow_mode") is False
    if not takeover_enabled:
        return []

    failures: list[str] = []
    if primary_llm.get("enabled") is not True:
        failures.append(f"{path}: disease_llm.shadow_mode=false requires primary_llm.enabled=true")
    if primary_llm.get("provider") == "mock":
        failures.append(f"{path}: primary_llm.provider must not be mock when disease LLM takeover is enabled")
    if not primary_llm.get("model"):
        failures.append(f"{path}: primary_llm.model is required when disease LLM takeover is enabled")
    if not primary_llm.get("base_url"):
        failures.append(f"{path}: primary_llm.base_url is required when disease LLM takeover is enabled")
    if not primary_llm.get("api_key_env"):
        failures.append(f"{path}: primary_llm.api_key_env is required when disease LLM takeover is enabled")
    return failures


def _check_batch_quality_report(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").lower()
    failures: list[str] = []
    for marker in ("quality gate: passed", "80/80 passed", "source_uri_coverage", "no_answer_accuracy"):
        if marker not in text:
            failures.append(f"{path}: missing quality marker: {marker}")
    return failures


def _check_run_eval_settings_arg(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "--settings" not in text or "load_settings" not in text:
        return [f"{path}: real eval must support explicit --settings override"]
    return []


def _missing_paths(root: Path, paths: tuple[str, ...]) -> list[str]:
    return [f"missing required file: {path}" for path in paths if not (root / path).exists()]


def _run_existing_check(args: list[str]) -> list[str]:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return []
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    return [f"{' '.join(args)} failed: {output}"]


def _find_case(payload: Any, task_type: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    for item in payload.get("cases") or []:
        if isinstance(item, dict) and item.get("task_type") == task_type:
            return item
    return None


if __name__ == "__main__":
    raise SystemExit(main())
