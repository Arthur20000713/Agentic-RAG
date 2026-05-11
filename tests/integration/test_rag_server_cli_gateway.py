from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.core.config import Settings, load_settings
from backend.app.integrations.rag_server.cli_gateway import RagServerCliGateway


def _test_dir() -> Path:
    path = Path(".tmp_tests") / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def test_cli_gateway_requires_rag_server_path(monkeypatch) -> None:
    monkeypatch.delenv("RAG_SERVER_PATH", raising=False)
    settings = load_settings("config/settings.test.yaml")

    result = RagServerCliGateway(settings).ingest("demo.pdf", dry_run=True)

    assert result.status == "failed"
    assert result.error_code == "RAG_SERVER_PATH_MISSING"


def test_cli_gateway_reports_missing_ingest_script(monkeypatch) -> None:
    root = _test_dir()
    monkeypatch.setenv("RAG_SERVER_PATH", str(root))
    settings = load_settings("config/settings.test.yaml")

    result = RagServerCliGateway(settings).ingest("demo.pdf", dry_run=True)

    assert result.status == "failed"
    assert result.error_code == "RAG_SERVER_INGEST_SCRIPT_MISSING"


@pytest.mark.rag_server
def test_real_rag_server_cli_ingest_dry_run_smoke() -> None:
    repo_path = os.getenv("RAG_SERVER_PATH")
    if not repo_path:
        pytest.skip("RAG_SERVER_PATH is required for real RAG-SERVER CLI smoke tests")

    repo_root = Path(repo_path)
    smoke_path = repo_root / "tests" / "fixtures"
    if not smoke_path.exists():
        smoke_path = repo_root

    settings = Settings(
        rag_server={
            "query_mode": "fake",
            "repo_path": str(repo_root),
            "python_executable": sys.executable,
            "collection": "default",
            "timeout_seconds": 30,
        }
    )

    result = RagServerCliGateway(settings).ingest(smoke_path, dry_run=True, collection="default", timeout_seconds=30)

    assert result.return_code is not None
    assert result.error_code not in {"RAG_SERVER_PATH_MISSING", "RAG_SERVER_INGEST_SCRIPT_MISSING", "RAG_INGEST_TIMEOUT"}
