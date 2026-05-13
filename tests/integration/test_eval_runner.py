from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

from backend.app.evaluation.golden_runner import GoldenSetRunner
from backend.app.evaluation.real_rag_runner import RealRagEvalRunner
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import EvalRunRepository
from backend.app.integrations.rag_server.mcp_stdio_client import RagServerMcpClient
from scripts.run_eval import main as run_eval_main


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_golden_set_runner_writes_reports() -> None:
    output_dir = _tmp_dir()
    runner = GoldenSetRunner(output_dir=output_dir)

    report = runner.run()
    runner.write_outputs(report)

    assert report.metrics["total_cases"] == 60
    assert report.metrics["failed_cases"] == 0
    assert report.metrics["intent_accuracy"] == 1.0
    assert (output_dir / "eval_result.json").exists()
    assert (output_dir / "eval_result.csv").exists()
    assert (output_dir / "eval_summary.md").exists()


def test_run_eval_script_outputs_expected_files() -> None:
    output_dir = _tmp_dir()

    exit_code = run_eval_main(["--output-dir", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "eval_result.json").exists()
    assert (output_dir / "eval_result.csv").exists()
    assert (output_dir / "eval_summary.md").read_text(encoding="utf-8").startswith("# Evaluation Summary")


def test_run_eval_script_accepts_fake_mode() -> None:
    output_dir = _tmp_dir()

    exit_code = run_eval_main(["--mode", "fake", "--output-dir", str(output_dir)])

    assert exit_code == 0
    assert (output_dir / "eval_result.json").exists()


def test_run_eval_real_rag_optional_writes_skipped_report_when_unconfigured(monkeypatch, capsys) -> None:  # noqa: ANN001
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    output_dir = _tmp_dir()

    exit_code = run_eval_main(["--mode", "real", "--optional", "--output-dir", str(output_dir)])

    assert exit_code == 0
    assert "SKIPPED" in capsys.readouterr().out
    payload = json.loads((output_dir / "eval_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert payload["mode"] == "real"
    assert payload["error_code"] == "RAG_SERVER_PATH_MISSING"
    assert (output_dir / "eval_result.csv").exists()
    assert (output_dir / "eval_summary.md").read_text(encoding="utf-8").startswith("# Real RAG Evaluation Summary")
    assert "RAG_SERVER_UNAVAILABLE" in (output_dir / "failure_analysis.md").read_text(encoding="utf-8")


def test_run_eval_real_rag_requires_configuration_without_optional(monkeypatch, capsys) -> None:  # noqa: ANN001
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)

    exit_code = run_eval_main(["--mode", "real"])

    assert exit_code == 2
    assert "RAG_SERVER_PATH" in capsys.readouterr().err


def test_real_rag_runner_creates_mcp_client_when_path_is_configured(monkeypatch) -> None:
    repo_path = _tmp_dir()
    run_local = repo_path / "scripts" / "run_local.ps1"
    run_local.parent.mkdir(parents=True, exist_ok=True)
    run_local.write_text(f'$Python = "{sys.executable}"\n', encoding="utf-8")
    monkeypatch.setenv("RAG_SERVER_PATH", str(repo_path))

    runner = RealRagEvalRunner(output_dir=_tmp_dir())
    client = runner.create_rag_client()

    assert isinstance(client, RagServerMcpClient)
    assert runner.settings.rag_server.query_mode == "real"
    assert runner.settings.rag_server.python_executable == sys.executable


def test_eval_run_log_repository_persists_metrics_and_failure_summary() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)
    repository = EvalRunRepository(conn)

    row_id = repository.add(
        run_id="eval_001",
        eval_type="golden",
        rag_mode="fake",
        total_cases=60,
        passed_cases=58,
        metrics={"pass_rate": 0.9667},
        failure_summary={"unsupported_claim": 2},
        report_path="reports/eval_summary.md",
    )
    stored = repository.get("eval_001")

    assert row_id > 0
    assert stored is not None
    assert stored["run_id"] == "eval_001"
    assert stored["total_cases"] == 60
    assert stored["passed_cases"] == 58
    assert stored["metrics"] == {"pass_rate": 0.9667}
    assert stored["failure_summary"] == {"unsupported_claim": 2}
    assert stored["report_path"] == "reports/eval_summary.md"
