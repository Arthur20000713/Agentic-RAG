from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("baseline", "corpus", "full")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight V4.1 contract checks.")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="baseline",
        help="V4.1 check stage. Checks are read-only and never start real RAG.",
    )
    parser.add_argument("--real-rag", action="store_true", help="run optional real RAG smoke checks")
    parser.add_argument("--real-rag-required", action="store_true", help="fail instead of skipping when real RAG is unavailable")
    parser.add_argument(
        "--real-rag-output-dir",
        type=Path,
        default=Path(".tmp_tests") / "v4_1_real_rag_smoke",
        help="output directory for optional real RAG smoke reports",
    )
    args = parser.parse_args(argv)

    failures = _check_stage(args.stage, ROOT)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    if args.real_rag:
        real_rag_code = run_real_rag_smoke(
            optional=not args.real_rag_required,
            output_dir=args.real_rag_output_dir,
        )
        if real_rag_code != 0:
            return real_rag_code

    print(f"V4.1 checks passed for stage {args.stage}")
    return 0


def check_required_files(root: Path) -> list[str]:
    return _missing_paths(
        root,
        [
            "README.md",
            "DEV_SPEC_v4_1.md",
            "docs/V4_1_BASELINE.md",
        ],
    )


def check_real_golden_sets(root: Path) -> list[str]:
    return _missing_paths(
        root,
        [
            "tests/fixtures/real_golden_v4_1/answerable.json",
            "tests/fixtures/real_golden_v4_1/no_answer.json",
            "tests/fixtures/real_golden_v4_1/safety.json",
        ],
    )


def check_source_manifest(root: Path) -> list[str]:
    return _missing_paths(root, ["docs/rag_corpus/source_manifest.yaml"])


def run_real_rag_smoke(optional: bool, output_dir: str | Path | None = None) -> int:
    resolved_output_dir = Path(output_dir) if output_dir is not None else ROOT / ".tmp_tests" / "v4_1_real_rag_smoke"
    if not resolved_output_dir.is_absolute():
        resolved_output_dir = ROOT / resolved_output_dir

    if not os.getenv("RAG_SERVER_PATH"):
        if optional:
            _write_skipped_real_rag_report(
                resolved_output_dir,
                error_code="RAG_SERVER_PATH_MISSING",
                reason="RAG_SERVER_PATH is not configured",
            )
            print(f"V4.1 real RAG smoke skipped: report={resolved_output_dir / 'eval_result.json'}")
            return 0
        print("FAIL: RAG_SERVER_PATH is not configured", file=sys.stderr)
        return 1

    smoke = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "rag_server", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if smoke.returncode != 0:
        if optional:
            _write_skipped_real_rag_report(
                resolved_output_dir,
                error_code="RAG_SERVER_SMOKE_FAILED",
                reason=_combined_output(smoke),
            )
            print(f"V4.1 real RAG smoke skipped: report={resolved_output_dir / 'eval_result.json'}")
            return 0
        print(_combined_output(smoke), file=sys.stderr)
        return smoke.returncode

    eval_run = subprocess.run(
        [
            sys.executable,
            "scripts/run_eval.py",
            "--mode",
            "real",
            "--optional",
            "--output-dir",
            str(resolved_output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if eval_run.returncode != 0:
        print(_combined_output(eval_run), file=sys.stderr)
        return eval_run.returncode

    failures = check_real_rag_report(resolved_output_dir)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(f"V4.1 real RAG smoke passed: report={resolved_output_dir / 'eval_result.json'}")
    return 0


def check_real_rag_report(output_dir: Path) -> list[str]:
    report_path = output_dir / "eval_result.json"
    if not report_path.exists():
        return [f"missing real RAG report: {report_path}"]
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid real RAG report JSON: {exc}"]

    failures: list[str] = []
    if payload.get("mode") != "real":
        failures.append("real RAG report must include mode=real")
    if payload.get("status") == "skipped":
        if not payload.get("error_code"):
            failures.append("skipped real RAG report must include error_code")
        if not payload.get("reason"):
            failures.append("skipped real RAG report must include reason")
    return failures


def _check_stage(stage: str, root: Path) -> list[str]:
    failures = check_required_files(root)

    if stage in {"corpus", "full"}:
        failures.extend(check_source_manifest(root))
        failures.extend(check_real_golden_sets(root))

    if stage == "full":
        failures.extend(_run_existing_check(root, ["scripts/check_v2.py", "--offline", "--frontend-contract", "--docs"]))
        failures.extend(_run_existing_check(root, ["scripts/check_v3.py", "--stage", "full"]))

    return failures


def _run_existing_check(root: Path, args: list[str]) -> list[str]:
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode == 0:
        return []
    output = _combined_output(completed)
    return [f"{' '.join(args)} failed: {output}"]


def _missing_paths(root: Path, paths: list[str]) -> list[str]:
    return [f"missing required file: {path}" for path in paths if not (root / path).exists()]


def _write_skipped_real_rag_report(output_dir: Path, *, error_code: str, reason: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "skipped",
        "mode": "real",
        "error_code": error_code,
        "reason": reason,
    }
    with (output_dir / "eval_result.json").open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def _combined_output(completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)


if __name__ == "__main__":
    raise SystemExit(main())
