from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from backend.app.core.config import Settings
from backend.app.integrations.rag_server.health import resolve_rag_server_path


COLLECTION_MISMATCH_WARNING = "RAG_COLLECTION_MISMATCH"


class RagServerDiagnostics(BaseModel):
    repo_path_configured: bool
    repo_path: str | None = None
    repo_path_exists: bool = False
    python_executable_configured: bool = False
    python_executable: str | None = None
    config_path: str | None = None
    config_exists: bool = False
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key_present: bool = False
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_api_key_present: bool = False
    vector_store_provider: str | None = None
    vector_store_collection: str | None = None
    agent_collection: str | None = None
    collection_mismatch: bool = False
    warnings: list[str] = Field(default_factory=list)


def build_rag_server_diagnostics(settings: Settings) -> RagServerDiagnostics:
    repo_path = resolve_rag_server_path(settings)
    python_executable = settings.rag_server.python_executable or os.getenv("RAG_SERVER_PYTHON")
    warnings: list[str] = []

    config: dict[str, Any] = {}
    config_path: Path | None = None
    config_exists = False
    if repo_path is not None:
        config_path = repo_path / "config" / "settings.yaml"
        config_exists = config_path.exists()
        if config_exists:
            config = _read_yaml(config_path)
        else:
            warnings.append("RAG_SERVER_CONFIG_MISSING")

    llm = _section(config, "llm")
    embedding = _section(config, "embedding")
    vector_store = _section(config, "vector_store")
    vector_collection = _optional_text(vector_store.get("collection_name"))
    agent_collection = settings.rag_server.collection
    collection_mismatch = bool(
        vector_collection
        and agent_collection
        and vector_collection != agent_collection
    )
    if collection_mismatch:
        warnings.append(COLLECTION_MISMATCH_WARNING)

    return RagServerDiagnostics(
        repo_path_configured=repo_path is not None,
        repo_path=str(repo_path) if repo_path is not None else None,
        repo_path_exists=bool(repo_path and repo_path.exists()),
        python_executable_configured=bool(python_executable),
        python_executable=python_executable,
        config_path=str(config_path) if config_path is not None else None,
        config_exists=config_exists,
        llm_provider=_optional_text(llm.get("provider")),
        llm_model=_optional_text(llm.get("model")),
        llm_api_key_present=_secret_present(llm),
        embedding_provider=_optional_text(embedding.get("provider")),
        embedding_model=_optional_text(embedding.get("model")),
        embedding_api_key_present=_secret_present(embedding),
        vector_store_provider=_optional_text(vector_store.get("provider")),
        vector_store_collection=vector_collection,
        agent_collection=agent_collection,
        collection_mismatch=collection_mismatch,
        warnings=warnings,
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data if isinstance(data, dict) else {}


def _section(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name)
    return value if isinstance(value, dict) else {}


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _secret_present(section: dict[str, Any]) -> bool:
    for key, value in section.items():
        lowered = str(key).lower()
        if any(token in lowered for token in ("api_key", "apikey", "secret", "token", "password")):
            return value not in (None, "")
    return False

