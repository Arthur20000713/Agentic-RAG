from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.evaluation.corpus_batch import CorpusBatch, load_corpus_batch, validate_corpus_batch
from backend.app.evaluation.source_manifest import SourceManifestEntry, load_source_manifest, validate_source_manifest


DEFAULT_MANIFEST = ROOT / "docs" / "rag_corpus" / "source_manifest.yaml"
DEFAULT_CORPUS_ROOT = Path(r"C:\tmp\livestock_corpus\batch_01")
INGESTIBLE_STATUSES = {"approved_summary_only", "approved_full_text"}


@dataclass(frozen=True)
class IngestCommand:
    source_id: str
    path: Path
    collection: str
    ingestion_mode: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run checks for RAG corpus ingestion.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--batch", type=Path, default=None)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--collection", default=None)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--require-files", action="store_true", help="fail if approved local corpus files are missing")
    args = parser.parse_args(argv)

    if args.batch is not None:
        return _run_batch_dry_run(args.batch, collection_override=args.collection, require_files=args.require_files)

    manifest_path = _resolve_path(args.manifest)
    corpus_root = args.corpus_root
    if not corpus_root.is_absolute():
        corpus_root = ROOT / corpus_root

    try:
        manifest = load_source_manifest(manifest_path)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    failures = validate_source_manifest(manifest)
    if args.require_files:
        failures.extend(validate_local_corpus_files(manifest.sources, corpus_root))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    collection = args.collection or manifest.collection or "default"
    commands = build_rag_server_ingest_commands(manifest.sources, collection, corpus_root=corpus_root)
    print("DRY-RUN: planned RAG-SERVER ingest commands")
    print(f"manifest: {manifest_path}")
    print(f"collection: {collection}")
    print(f"corpus_root: {corpus_root}")
    if not commands:
        print("no ingestible sources found")
    for command in commands:
        print(command)
    return 0


def load_batch_or_manifest(path: Path) -> CorpusBatch | object:
    resolved_path = _resolve_path(path)
    with resolved_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file) or {}
    if not isinstance(payload, dict):
        raise ValueError("corpus input must be a YAML mapping")
    if "batch_id" in payload:
        return load_corpus_batch(resolved_path)
    return load_source_manifest(resolved_path)


def build_ingest_plan(batch: CorpusBatch, *, collection_override: str | None = None) -> list[IngestCommand]:
    collection = collection_override or batch.collection or "default"
    commands: list[IngestCommand] = []
    for source in batch.sources:
        if not source.source_id or not source.local_file or not source.ingestion_mode:
            continue
        path = Path(source.local_file)
        if not path.is_absolute():
            path = ROOT / path
        commands.append(
            IngestCommand(
                source_id=source.source_id,
                path=path,
                collection=collection,
                ingestion_mode=source.ingestion_mode,
            )
        )
    return commands


def render_ingest_plan(commands: list[IngestCommand]) -> str:
    lines: list[str] = []
    for command in commands:
        lines.append(
            f'python scripts/ingest.py --path "{command.path}" --collection "{command.collection}"'
            f" # source_id={command.source_id} mode={command.ingestion_mode}"
        )
    return "\n".join(lines)


def collect_manifest_sources(manifest_path: Path) -> list[SourceManifestEntry]:
    manifest = load_source_manifest(manifest_path)
    failures = validate_source_manifest(manifest)
    if failures:
        raise ValueError("\n".join(failures))
    return manifest.sources


def validate_local_corpus_files(entries: list[SourceManifestEntry], corpus_root: Path) -> list[str]:
    failures: list[str] = []
    for entry in entries:
        if entry.ingestion_status not in INGESTIBLE_STATUSES:
            continue
        expected_path = _entry_corpus_path(entry, corpus_root)
        if not expected_path.exists():
            failures.append(f"missing local corpus file for {entry.source_id}: {expected_path}")
    return failures


def build_rag_server_ingest_commands(
    entries: list[SourceManifestEntry],
    collection: str,
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
) -> list[str]:
    commands: list[str] = []
    for entry in entries:
        if entry.ingestion_status not in INGESTIBLE_STATUSES:
            continue
        path = _entry_corpus_path(entry, corpus_root)
        commands.append(f'python scripts/ingest.py --path "{path}" --collection "{collection}"')
    return commands


def _entry_corpus_path(entry: SourceManifestEntry, corpus_root: Path) -> Path:
    if entry.local_path:
        return Path(entry.local_path)
    return corpus_root / f"{entry.source_id}.md"


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT / path


def _run_batch_dry_run(batch_path: Path, *, collection_override: str | None, require_files: bool) -> int:
    resolved_batch_path = _resolve_path(batch_path)
    try:
        loaded = load_batch_or_manifest(resolved_batch_path)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if not isinstance(loaded, CorpusBatch):
        print(f"FAIL: --batch must point to a corpus batch file: {resolved_batch_path}", file=sys.stderr)
        return 1

    failures = validate_corpus_batch(loaded, require_files=require_files)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    commands = build_ingest_plan(loaded, collection_override=collection_override)
    collection = collection_override or loaded.collection or "default"
    print("DRY-RUN: planned RAG-SERVER ingest commands")
    print(f"batch: {resolved_batch_path}")
    print(f"batch_id: {loaded.batch_id}")
    print(f"manifest: {loaded.manifest}")
    print(f"collection: {collection}")
    if not commands:
        print("no batch sources found")
    else:
        print(render_ingest_plan(commands))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
