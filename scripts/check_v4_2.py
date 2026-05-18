from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.evaluation.corpus_batch import load_corpus_batch, validate_corpus_batch
from backend.app.evaluation.golden_runner import GoldenCase
from backend.app.evaluation.source_manifest import load_source_manifest, validate_source_manifest


STAGES = ("batch", "eval", "gate", "full")
BATCH_DIR = Path("docs") / "rag_corpus" / "batches"
REPORT_DIR = Path("docs") / "rag_corpus" / "reports"
REAL_GOLDEN_V4_2_DIR = Path("tests") / "fixtures" / "real_golden_v4_2"
REQUIRED_FILES = (
    "DEV_SPEC_v4_2.md",
    "docs/rag_corpus/source_manifest.yaml",
)
REQUIRED_REPORT_MARKERS = (
    "batch id:",
    "collection:",
    "source count:",
    "ingestion status:",
    "preflight status:",
    "eval summary:",
    "failure categories:",
)
REAL_GOLDEN_V4_2_FILES = (
    "answerable.json",
    "no_answer.json",
    "safety.json",
    "bilingual.json",
    "all.json",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight V4.2 contract checks.")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        default="batch",
        help="V4.2 check stage. Checks are read-only and never start real RAG.",
    )
    args = parser.parse_args(argv)

    failures = _check_stage(args.stage, ROOT)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print(f"V4.2 checks passed for stage {args.stage}")
    return 0


def check_batch_files(root: Path) -> list[str]:
    failures: list[str] = []
    batch_paths = _batch_paths(root)
    if batch_paths is None:
        return failures
    if not batch_paths:
        return [f"missing corpus batch YAML files under: {root / BATCH_DIR}"]

    for batch_path in batch_paths:
        try:
            batch = load_corpus_batch(batch_path)
        except (OSError, ValueError) as exc:
            failures.append(f"{batch_path}: {exc}")
            continue
        for failure in validate_corpus_batch(batch, require_files=_requires_local_files(batch.status)):
            failures.append(f"{batch_path}: {failure}")
    return failures


def check_manifest_alignment(root: Path) -> list[str]:
    failures: list[str] = []
    batch_paths = _batch_paths(root)
    if not batch_paths:
        return failures

    for batch_path in batch_paths:
        try:
            batch = load_corpus_batch(batch_path)
        except (OSError, ValueError) as exc:
            failures.append(f"{batch_path}: {exc}")
            continue
        if not batch.manifest:
            continue

        manifest_path = _resolve_under_root(root, batch.manifest)
        try:
            manifest = load_source_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            failures.append(f"{batch_path}: manifest {manifest_path}: {exc}")
            continue

        for failure in validate_source_manifest(manifest):
            failures.append(f"{manifest_path}: {failure}")

        if batch.collection and manifest.collection and batch.collection != manifest.collection:
            failures.append(
                f"{batch_path}: collection mismatch: batch={batch.collection}, manifest={manifest.collection}"
            )

        manifest_source_ids = {source.source_id for source in manifest.sources if source.source_id}
        for source in batch.sources:
            if source.source_id and source.source_id not in manifest_source_ids:
                failures.append(f"{batch_path}: source_id {source.source_id} not found in manifest {manifest_path}")
    return failures


def check_batch_report(batch_id: str, root: Path) -> list[str]:
    report_path = root / REPORT_DIR / f"{batch_id}_quality.md"
    if not report_path.exists():
        return [f"missing batch quality report: {report_path}"]

    text = report_path.read_text(encoding="utf-8").lower()
    failures: list[str] = []
    for marker in REQUIRED_REPORT_MARKERS:
        if marker not in text:
            failures.append(f"{report_path}: missing required report field: {marker.rstrip(':')}")
    return failures


def check_real_golden_v4_2(root: Path) -> list[str]:
    fixture_dir = root / REAL_GOLDEN_V4_2_DIR
    failures = check_golden_distribution(fixture_dir)
    if failures:
        return failures

    failures.extend(check_golden_source_ids(fixture_dir / "all.json", root / "docs" / "rag_corpus" / "manifests" / "livestock_v4_2.yaml"))
    return failures


def check_golden_source_ids(golden_path: Path, manifest_path: Path) -> list[str]:
    failures: list[str] = []
    manifest = load_source_manifest(manifest_path)
    manifest_failures = validate_source_manifest(manifest)
    if manifest_failures:
        return [f"{manifest_path}: {failure}" for failure in manifest_failures]

    manifest_source_ids = {source.source_id for source in manifest.sources if source.source_id}
    for case in _load_golden_cases(golden_path):
        for source_id in case.source_ids:
            if source_id not in manifest_source_ids:
                failures.append(f"{case.case_id} source_id {source_id} not found in manifest")
    return failures


def check_golden_distribution(golden_dir: Path) -> list[str]:
    failures: list[str] = []
    grouped_cases: dict[str, list[GoldenCase]] = {}
    for filename in REAL_GOLDEN_V4_2_FILES:
        path = golden_dir / filename
        if not path.exists():
            failures.append(f"missing V4.2 real golden file: {path}")
            continue
        try:
            grouped_cases[filename] = _load_golden_cases(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{path}: {exc}")

    if failures:
        return failures

    distribution_requirements = {
        "answerable.json": 35,
        "no_answer.json": 20,
        "safety.json": 15,
        "bilingual.json": 10,
        "all.json": 80,
    }
    below_minimums: list[str] = []
    for filename, minimum in distribution_requirements.items():
        actual = len(grouped_cases[filename])
        if actual < minimum:
            below_minimums.append(f"{filename.removesuffix('.json')}={actual}/{minimum}")
    if below_minimums:
        failures.append(f"V4.2 golden distribution below minimums: {', '.join(below_minimums)}")

    for filename, cases in grouped_cases.items():
        for case in cases:
            if case.expected_answer_type == "answerable" and not case.source_ids:
                failures.append(f"{golden_dir / filename}: answerable case {case.case_id} missing source_ids")
    return failures


def _check_stage(stage: str, root: Path) -> list[str]:
    failures = _missing_paths(root, REQUIRED_FILES)

    if stage in {"batch", "full"}:
        failures.extend(check_batch_files(root))
        failures.extend(check_manifest_alignment(root))
        failures.extend(_check_batch_reports(root))

    if stage in {"eval", "full"}:
        failures.extend(check_real_golden_v4_2(root))

    if stage == "full":
        failures.extend(_run_existing_check(root, ["scripts/check_v4_1.py", "--stage", "full"]))

    return failures


def _batch_paths(root: Path) -> list[Path] | None:
    batch_dir = root / BATCH_DIR
    if not batch_dir.exists():
        return None
    return sorted(batch_dir.glob("*.yaml"))


def _check_batch_reports(root: Path) -> list[str]:
    failures: list[str] = []
    batch_paths = _batch_paths(root)
    if not batch_paths:
        return failures
    for batch_path in batch_paths:
        try:
            batch = load_corpus_batch(batch_path)
        except (OSError, ValueError):
            continue
        if batch.batch_id:
            failures.extend(check_batch_report(batch.batch_id, root))
    return failures


def _requires_local_files(batch_status: str | None) -> bool:
    return batch_status not in {"planned", "not_ingested"}


def _missing_paths(root: Path, paths: tuple[str, ...]) -> list[str]:
    return [f"missing required file: {path}" for path in paths if not (root / path).exists()]


def _resolve_under_root(root: Path, path: str) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return root / resolved


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


def _load_golden_cases(path: Path) -> list[GoldenCase]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("golden set must be a JSON list")
    return [GoldenCase.model_validate(item) for item in payload]


if __name__ == "__main__":
    raise SystemExit(main())
