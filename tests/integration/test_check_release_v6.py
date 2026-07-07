from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.check_release_v6 import run_release_checks


def test_run_release_checks_reports_usable_when_required_steps_pass(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(args: list[str], log_path: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if any(arg.endswith("run_local_model_smoke.py") for arg in args):
            output_path = Path(args[args.index("--output") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                '{"status":"passed","provider":"transformers","cases":[{"task_type":"query_normalization","status":"passed","fallback_required":false}]}',
                encoding="utf-8",
            )
        log_path.write_text("ok", encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    report = run_release_checks(tmp_path, python_path="python", command_runner=fake_runner)

    assert report["status"] == "usable"
    assert [step["name"] for step in report["steps"]] == [
        "runtime_doctor",
        "v6_full_check",
        "local_model_smoke",
        "pytest_not_rag_server",
    ]
    assert any("scripts/run_local_model_smoke.py" in call for call in calls)


def test_run_release_checks_rejects_skipped_local_model_report(tmp_path: Path) -> None:
    def fake_runner(args: list[str], log_path: Path) -> subprocess.CompletedProcess[str]:
        if any(arg.endswith("run_local_model_smoke.py") for arg in args):
            output_path = Path(args[args.index("--output") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text('{"status":"skipped","reason":"missing"}', encoding="utf-8")
        log_path.write_text("ok", encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    report = run_release_checks(tmp_path, python_path="python", command_runner=fake_runner)

    assert report["status"] == "not_usable"
    assert report["steps"][2]["name"] == "local_model_smoke"
    assert report["steps"][2]["status"] == "failed"
    assert report["steps"][2]["reason"] == "local model smoke did not pass"
