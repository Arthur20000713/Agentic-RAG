from __future__ import annotations

import argparse
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
    args = parser.parse_args(argv)

    failures = _check_stage(args.stage, ROOT)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

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
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    return [f"{' '.join(args)} failed: {output}"]


def _missing_paths(root: Path, paths: list[str]) -> list[str]:
    return [f"missing required file: {path}" for path in paths if not (root / path).exists()]


if __name__ == "__main__":
    raise SystemExit(main())
