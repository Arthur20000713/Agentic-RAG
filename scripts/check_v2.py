from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lightweight V2 contract checks.")
    parser.add_argument("--offline", action="store_true", help="check V2 offline development prerequisites")
    parser.add_argument("--frontend-contract", action="store_true", help="check the V2.3 static frontend contract")
    parser.add_argument("--docs", action="store_true", help="check V2 delivery documentation")
    args = parser.parse_args(argv)

    if not any((args.offline, args.frontend_contract, args.docs)):
        args.offline = True

    failures: list[str] = []
    if args.offline:
        failures.extend(_check_offline_contract())
    if args.frontend_contract:
        failures.extend(_check_frontend_contract())
    if args.docs:
        failures.extend(_check_docs_contract())

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    print("V2 checks passed")
    return 0


def _check_offline_contract() -> list[str]:
    failures: list[str] = []
    required_files = [
        "DEV_SPEC.md",
        "pyproject.toml",
        ".gitignore",
        "scripts/run_eval.py",
        "scripts/check_all.py",
        "config/settings.yaml",
        "docs/API_SPEC.md",
        "docs/MCP_SPEC.md",
        "docs/RAG_SERVER_INTEGRATION.md",
        "docs/SAFETY_SPEC.md",
        "docs/HARNESS.md",
    ]
    failures.extend(_missing_files(required_files))

    gitignore = _read_text(".gitignore")
    if ".venv/" not in gitignore:
        failures.append(".gitignore must ignore .venv/")

    settings = _read_text("config/settings.yaml")
    if "rag_server:" not in settings:
        failures.append("config/settings.yaml must keep the rag_server section")
    if "rag:" in settings:
        failures.append("config/settings.yaml must not introduce a parallel rag.* section")

    run_eval = _read_text("scripts/run_eval.py")
    if "--mode" not in run_eval or '"fake"' not in run_eval:
        failures.append("scripts/run_eval.py must support --mode fake")

    dev_spec = _read_text("DEV_SPEC.md")
    for required_text in (
        "V2.1-A0",
        "rag_server.repo_path",
        "真实 MCP 响应解析规则",
        "V2.2 与 V1 现有类迁移关系",
        "Session Context 契约",
        "简体中文 commit",
    ):
        if required_text not in dev_spec:
            failures.append(f"DEV_SPEC.md is missing required V2 contract text: {required_text}")

    return failures


def _check_frontend_contract() -> list[str]:
    required_files = [
        "backend/app/static/frontend/index.html",
        "backend/app/static/frontend/app.js",
        "backend/app/static/frontend/styles.css",
        "docs/FRONTEND_SPEC.md",
    ]
    return _missing_files(required_files)


def _check_docs_contract() -> list[str]:
    required_files = [
        "README.md",
        "docs/API_SPEC.md",
        "docs/MCP_SPEC.md",
        "docs/RAG_SERVER_INTEGRATION.md",
        "docs/SAFETY_SPEC.md",
        "docs/EVAL_SPEC.md",
        "docs/HARNESS.md",
        "docs/INTERVIEW_NOTES.md",
        "docs/DEMO_SCRIPT.md",
    ]
    return _missing_files(required_files)


def _missing_files(paths: list[str]) -> list[str]:
    return [f"missing required file: {path}" for path in paths if not (ROOT / path).exists()]


def _read_text(path: str) -> str:
    candidate = ROOT / path
    if not candidate.exists():
        return ""
    return candidate.read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
