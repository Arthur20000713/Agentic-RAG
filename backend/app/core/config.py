from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"


class RagServerSettings(BaseModel):
    query_mode: Literal["fake", "mcp_stdio"] = "fake"
    repo_path: str | None = None
    python_executable: str | None = None
    collection: str = "default"
    timeout_seconds: float = 5.0


class DatabaseSettings(BaseModel):
    url: str = "sqlite:///data/app.db"


class AppSettings(BaseModel):
    name: str = "Livestock Agentic RAG"
    environment: str = "local"
    debug: bool = False


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    rag_server: RagServerSettings = Field(default_factory=RagServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"settings file must contain a mapping: {path}")
    return data


def load_settings(path: str | Path | None = None) -> Settings:
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.is_absolute():
        settings_path = PROJECT_ROOT / settings_path

    raw = _read_yaml(settings_path)
    settings = Settings.model_validate(raw)

    # Query mode remains config-driven; only the real RAG-SERVER path can be
    # injected from the environment according to DEV_SPEC precedence.
    env_rag_path = os.getenv("RAG_SERVER_PATH")
    if env_rag_path:
        settings.rag_server.repo_path = env_rag_path
    return settings


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate
