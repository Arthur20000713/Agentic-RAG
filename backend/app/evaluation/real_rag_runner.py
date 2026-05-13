from __future__ import annotations

import asyncio
import csv
import json
import os
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT, Settings, load_settings
from backend.app.evaluation.failure_analysis import build_failure_report
from backend.app.evaluation.golden_runner import EvaluationReport, GoldenSetRunner
from backend.app.integrations.rag_server import create_rag_server_client
from backend.app.integrations.rag_server.base import RagServerClient
from backend.app.integrations.rag_server.health import resolve_rag_server_path


class RealRagEvalUnavailable(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message

    def to_payload(self) -> dict[str, str]:
        return {
            "status": "skipped",
            "mode": "real",
            "error_code": self.error_code,
            "reason": self.message,
        }


class RealRagEvalRunner:
    def __init__(
        self,
        golden_set_path: str | Path | None = None,
        *,
        output_dir: str | Path | None = None,
        settings: Settings | None = None,
        rag_client: RagServerClient | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.settings.rag_server.query_mode = "real"
        self.golden_set_path = golden_set_path
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "reports"
        if not self.output_dir.is_absolute():
            self.output_dir = PROJECT_ROOT / self.output_dir
        self.rag_client = rag_client

    def run(self) -> EvaluationReport:
        client = self.create_rag_client()
        try:
            runner = GoldenSetRunner(self.golden_set_path, output_dir=self.output_dir, rag_client=client)
            return runner.run()
        finally:
            if self.rag_client is None:
                close = getattr(client, "close", None)
                if close is not None:
                    asyncio.run(close())

    def write_outputs(self, report: EvaluationReport) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(report)
        self._write_csv(report)
        self._write_summary(report)
        build_failure_report(report, self.output_dir / "failure_analysis.md")

    def create_rag_client(self) -> RagServerClient:
        if self.rag_client is not None:
            return self.rag_client
        repo_path = self._require_repo_path()
        self._resolve_python_executable(repo_path)
        return create_rag_server_client(self.settings)

    def write_skipped_report(self, unavailable: RealRagEvalUnavailable) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        payload = unavailable.to_payload()
        with (self.output_dir / "eval_result.json").open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        with (self.output_dir / "eval_result.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["status", "mode", "error_code", "reason"])
            writer.writeheader()
            writer.writerow(payload)
        (self.output_dir / "eval_summary.md").write_text(
            "\n".join(
                [
                    "# Real RAG Evaluation Summary",
                    "",
                    "- Status: skipped",
                    f"- Error code: {unavailable.error_code}",
                    f"- Reason: {unavailable.message}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        build_failure_report(payload, self.output_dir / "failure_analysis.md")

    def _require_repo_path(self) -> Path:
        repo_path = resolve_rag_server_path(self.settings)
        if repo_path is None:
            raise RealRagEvalUnavailable(
                "RAG_SERVER_PATH_MISSING",
                "RAG_SERVER_PATH or rag_server.repo_path is required for real RAG evaluation",
            )
        if not repo_path.exists():
            raise RealRagEvalUnavailable(
                "RAG_SERVER_PATH_NOT_FOUND",
                f"RAG-SERVER path does not exist: {repo_path}",
            )
        return repo_path

    def _resolve_python_executable(self, repo_path: Path) -> None:
        if self.settings.rag_server.python_executable:
            return
        env_python = os.getenv("RAG_SERVER_PYTHON")
        if env_python:
            self.settings.rag_server.python_executable = env_python
            return
        local_python = self._python_from_run_local(repo_path)
        if local_python is not None:
            self.settings.rag_server.python_executable = str(local_python)

    def _python_from_run_local(self, repo_path: Path) -> Path | None:
        script = repo_path / "scripts" / "run_local.ps1"
        if not script.exists():
            return None
        for line in script.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("$Python"):
                continue
            raw_path = line.split("=", 1)[1].strip().strip("\"'")
            candidate = Path(raw_path)
            if candidate.exists():
                return candidate
        return None

    def _write_json(self, report: EvaluationReport) -> None:
        with (self.output_dir / "eval_result.json").open("w", encoding="utf-8") as file:
            json.dump(report.model_dump(), file, ensure_ascii=False, indent=2)
            file.write("\n")

    def _write_csv(self, report: EvaluationReport) -> None:
        with (self.output_dir / "eval_result.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["case_id", "category", "passed", "intent", "risk_level", "tools_used", "checks", "errors"],
            )
            writer.writeheader()
            for item in report.cases:
                writer.writerow(
                    {
                        "case_id": item.case_id,
                        "category": item.category,
                        "passed": item.passed,
                        "intent": item.intent,
                        "risk_level": item.risk_level or "",
                        "tools_used": "|".join(item.tools_used),
                        "checks": json.dumps(item.checks, ensure_ascii=False, sort_keys=True),
                        "errors": "|".join(item.errors),
                    }
                )

    def _write_summary(self, report: EvaluationReport) -> None:
        metrics = report.metrics
        lines = [
            "# Real RAG Evaluation Summary",
            "",
            f"- Total cases: {metrics['total_cases']}",
            f"- Passed cases: {metrics['passed_cases']}",
            f"- Failed cases: {metrics['failed_cases']}",
            f"- Pass rate: {metrics['pass_rate']:.2%}",
            "",
            "## Metrics",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
        for key in (
            "intent_accuracy",
            "rag_call_accuracy",
            "citation_coverage",
            "no_answer_accuracy",
            "safety_pass_rate",
            "follow_up_accuracy",
            "structure_completeness",
        ):
            lines.append(f"| {key} | {metrics[key]:.2%} |")
        lines.extend(["", "## Categories", "", "| Category | Passed | Total | Pass rate |", "|---|---:|---:|---:|"])
        for category, item in metrics["by_category"].items():
            lines.append(f"| {category} | {item['passed']} | {item['total']} | {item['pass_rate']:.2%} |")
        lines.extend(["", "## Failure Categories", "", "| Category | Count |", "|---|---:|"])
        for category, count in metrics.get("failure_categories", {}).items():
            lines.append(f"| {category} | {count} |")
        (self.output_dir / "eval_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
