from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"


RagQueryMode = Literal["fake", "smoke", "real", "mcp_stdio"]
NormalizedRagQueryMode = Literal["fake", "smoke", "real"]


class RagServerSettings(BaseModel):
    query_mode: RagQueryMode = "fake"
    repo_path: str | None = None
    python_executable: str | None = None
    collection: str = "default"
    timeout_seconds: float = 5.0
    strict_real_mode: bool = False
    min_mapped_score: float = 0.03
    min_citation_count_for_answer: int = 1
    low_confidence_no_answer: bool = True

    @property
    def normalized_query_mode(self) -> NormalizedRagQueryMode:
        if self.query_mode == "mcp_stdio":
            return "real"
        return self.query_mode

    @property
    def uses_real_rag_server(self) -> bool:
        return self.query_mode in {"smoke", "real", "mcp_stdio"}


class DatabaseSettings(BaseModel):
    url: str = "sqlite:///data/app.db"


class AppSettings(BaseModel):
    name: str = "Livestock Agentic RAG"
    environment: str = "local"
    debug: bool = False


class V3Settings(BaseModel):
    enabled: bool = False


class ModelRouterSettings(BaseModel):
    enabled: bool = False
    shadow_mode: bool = True
    allow_low_risk_takeover: bool = False
    takeover_task_types: list[str] = Field(
        default_factory=lambda: ["query_normalization", "structured_extraction", "measurement_analysis", "summarization"]
    )
    blocked_safety_levels: list[str] = Field(default_factory=lambda: ["S3", "S4"])


class LocalModelSettings(BaseModel):
    enabled: bool = False
    provider: str = "mock"
    endpoint: str | None = None
    model: str | None = None
    timeout_seconds: float = 3.0
    max_retries: int = 0
    allow_final_answer: bool = False
    device: str = "auto"
    torch_dtype: str = "auto"
    max_new_tokens: int = 128
    temperature: float = 0.0


class PrimaryLLMSettings(BaseModel):
    enabled: bool = False
    provider: str = "mock"
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 0


class DiseaseLLMSettings(BaseModel):
    enabled: bool = False
    shadow_mode: bool = True
    require_rag_evidence: bool = True
    allow_rule_fallback: bool = True


class LoraSettings(BaseModel):
    dataset_enabled: bool = False
    inference_enabled: bool = False
    registry_path: str = "data/v3/model_registry.json"


class LongTermMemorySettings(BaseModel):
    write_enabled: bool = False
    read_enabled: bool = False
    ttl_days: int = 365


class EnhancedSafetySettings(BaseModel):
    precheck_enabled: bool = True
    final_guard_required: bool = True


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    rag_server: RagServerSettings = Field(default_factory=RagServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    v3: V3Settings = Field(default_factory=V3Settings)
    model_router: ModelRouterSettings = Field(default_factory=ModelRouterSettings)
    local_model: LocalModelSettings = Field(default_factory=LocalModelSettings)
    primary_llm: PrimaryLLMSettings = Field(default_factory=PrimaryLLMSettings)
    disease_llm: DiseaseLLMSettings = Field(default_factory=DiseaseLLMSettings)
    lora: LoraSettings = Field(default_factory=LoraSettings)
    long_term_memory: LongTermMemorySettings = Field(default_factory=LongTermMemorySettings)
    enhanced_safety: EnhancedSafetySettings = Field(default_factory=EnhancedSafetySettings)


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
