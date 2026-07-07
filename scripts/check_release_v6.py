from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run V6 product release acceptance checks.")
    parser.add_argument("--output-dir", default=".tmp_tests/v6_release", help="directory for logs and summary")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    parser.add_argument("--skip-pytest", action="store_true", help="skip the not-rag_server regression suite")
    args = parser.parse_args(argv)

    report = run_release_checks(
        Path(args.output_dir),
        python_path=args.python,
        skip_pytest=args.skip_pytest,
    )
    summary_path = Path(args.output_dir) / "release_check_summary.json"
    print(f"V6 release status: {report['status']}")
    print(f"Summary: {summary_path}")
    return 0 if report["status"] == "usable" else 1


def run_release_checks(
    output_dir: Path,
    *,
    python_path: str,
    command_runner: CommandRunner | None = None,
    skip_pytest: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = command_runner or _run_command
    steps: list[dict[str, Any]] = []

    required_steps: list[tuple[str, list[str]]] = [
        ("runtime_doctor", [python_path, "scripts/doctor_v6.py", "--json"]),
        ("v6_full_check", [python_path, "scripts/check_v6.py", "--stage", "full"]),
    ]
    local_model_report = output_dir / "local_model_smoke.json"
    required_steps.append(
        (
            "local_model_smoke",
            [
                python_path,
                "scripts/run_local_model_smoke.py",
                "--optional",
                "--output",
                str(local_model_report),
            ],
        )
    )
    if not skip_pytest:
        required_steps.append(("pytest_not_rag_server", [python_path, "-m", "pytest", "-m", "not rag_server", "-q"]))

    for name, command in required_steps:
        log_path = output_dir / f"{name}.log"
        completed = runner(command, log_path)
        step = {
            "name": name,
            "status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "command": command,
            "log": str(log_path),
        }
        if name == "local_model_smoke" and step["status"] == "passed":
            smoke_passed = _local_model_smoke_passed(local_model_report)
            if not smoke_passed:
                step["status"] = "failed"
                step["reason"] = "local model smoke did not pass"
        steps.append(step)

    status = "usable" if all(step["status"] == "passed" for step in steps) else "not_usable"
    report = {"status": status, "steps": steps}
    (output_dir / "release_check_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def _run_command(args: list[str], log_path: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    log_path.write_text(
        "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part),
        encoding="utf-8",
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    return completed


def _local_model_smoke_passed(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    query_case = _find_case(payload, "query_normalization")
    return (
        isinstance(payload, dict)
        and payload.get("status") == "passed"
        and payload.get("provider") == "transformers"
        and query_case is not None
        and query_case.get("status") == "passed"
        and query_case.get("fallback_required") is False
    )


def _find_case(payload: Any, task_type: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    for item in payload.get("cases") or []:
        if isinstance(item, dict) and item.get("task_type") == task_type:
            return item
    return None


if __name__ == "__main__":
    raise SystemExit(main())
