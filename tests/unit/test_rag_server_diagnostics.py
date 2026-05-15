from __future__ import annotations

from uuid import uuid4
from pathlib import Path

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.diagnostics import build_rag_server_diagnostics


def _tmp_dir() -> Path:
    path = Path(".tmp_tests") / f"v4_diag_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_rag_server_diagnostics_redacts_secret_values_and_detects_collection_mismatch() -> None:
    repo_path = _tmp_dir() / "RAG-SERVER"
    config_path = repo_path / "config" / "settings.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "llm:",
                "  provider: openai",
                "  model: gpt-4o",
                "  api_key: sk-real-value",
                "embedding:",
                "  provider: local",
                "  model: local-hash-embedding",
                "vector_store:",
                "  provider: chroma",
                "  collection_name: knowledge_hub",
                "",
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(
        rag_server={
            "query_mode": "real",
            "repo_path": str(repo_path),
            "python_executable": "python",
            "collection": "default",
        }
    )

    diagnostics = build_rag_server_diagnostics(settings)
    payload = diagnostics.model_dump()

    assert payload["repo_path_exists"] is True
    assert payload["config_exists"] is True
    assert payload["llm_provider"] == "openai"
    assert payload["llm_model"] == "gpt-4o"
    assert payload["llm_api_key_present"] is True
    assert "api_key" not in payload
    assert "sk-real-value" not in str(payload)
    assert payload["embedding_model"] == "local-hash-embedding"
    assert payload["vector_store_collection"] == "knowledge_hub"
    assert payload["agent_collection"] == "default"
    assert payload["collection_mismatch"] is True
    assert "RAG_COLLECTION_MISMATCH" in payload["warnings"]
