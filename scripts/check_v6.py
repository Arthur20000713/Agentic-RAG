from __future__ import annotations

import argparse
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
    workflow_test = root / "tests" / "integration" / "test_agent_workflow.py"
    failures.extend(
        _missing_paths(
            root,
            (
                "backend/app/model/answer_generator.py",
                "tests/unit/test_answer_generator.py",
                "tests/integration/test_agent_workflow.py",
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
    if workflow_test.exists():
        text = workflow_test.read_text(encoding="utf-8")
        for marker in ("ResultDumpRagClient", "Query Results", "source_uri"):
            if marker not in text:
                failures.append(f"{workflow_test}: missing workflow answer quality test marker: {marker}")
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


if __name__ == "__main__":
    raise SystemExit(main())
