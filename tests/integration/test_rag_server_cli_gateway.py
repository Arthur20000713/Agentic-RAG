from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.app.core.config import load_settings
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
