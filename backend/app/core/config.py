from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr


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


class InternalApiSettings(BaseModel):
    service_token: SecretStr | None = None
    execution_ttl_hours: int = Field(default=24, ge=1, le=168)
    execution_database_url: str | None = None
    shared_upload_root: str = "data/uploads"
    ingestion_worker_enabled: bool = True
    ingestion_poll_interval_seconds: float = Field(default=0.2, ge=0.05, le=30)
    ingestion_lease_seconds: int = Field(default=90, ge=5, le=3600)
    ingestion_timeout_seconds: int = Field(default=300, ge=5, le=3600)


class AgentRuntimeSettings(BaseModel):
    engine: Literal["langgraph"] = "langgraph"


class ModelRouterSettings(BaseModel):
    enabled: bool = False
    shadow_mode: bool = True
    allow_low_risk_takeover: bool = False
    takeover_task_types: list[str] = Field(
        default_factory=lambda: ["intent_routing", "query_normalization", "measurement_analysis", "summarization"]
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
    registry_path: str = "data/model_registry/model_registry.json"


class LongTermMemorySettings(BaseModel):
    write_enabled: bool = False
    read_enabled: bool = False
    ttl_days: int = 365


class EnhancedSafetySettings(BaseModel):
    precheck_enabled: bool = True
    final_guard_required: bool = True


class LegacyApiSettings(BaseModel):
    measurement_enabled: bool = False


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app: AppSettings = Field(default_factory=AppSettings)
    rag_server: RagServerSettings = Field(default_factory=RagServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    internal_api: InternalApiSettings = Field(default_factory=InternalApiSettings)
    agent_runtime: AgentRuntimeSettings = Field(default_factory=AgentRuntimeSettings)
    model_router: ModelRouterSettings = Field(default_factory=ModelRouterSettings)
    local_model: LocalModelSettings = Field(default_factory=LocalModelSettings)
    primary_llm: PrimaryLLMSettings = Field(default_factory=PrimaryLLMSettings)
    disease_llm: DiseaseLLMSettings = Field(default_factory=DiseaseLLMSettings)
    lora: LoraSettings = Field(default_factory=LoraSettings)
    long_term_memory: LongTermMemorySettings = Field(default_factory=LongTermMemorySettings)
    enhanced_safety: EnhancedSafetySettings = Field(default_factory=EnhancedSafetySettings)
    legacy_api: LegacyApiSettings = Field(default_factory=LegacyApiSettings)


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"settings file must contain a mapping: {path}")
    return data


def load_settings(path: str | Path | None = None) -> Settings:
    configured_path = path if path is not None else os.getenv("APP_SETTINGS_PATH")
    settings_path = Path(configured_path) if configured_path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.is_absolute():
        settings_path = PROJECT_ROOT / settings_path

    raw = _read_yaml(settings_path)
    settings = Settings.model_validate(raw)

    env_rag_path = os.getenv("RAG_SERVER_PATH")
    if env_rag_path:
        settings.rag_server.repo_path = env_rag_path
    env_rag_query_mode = os.getenv("RAG_QUERY_MODE")
    if env_rag_query_mode:
        if env_rag_query_mode not in {"fake", "smoke", "real", "mcp_stdio"}:
            raise ValueError(f"invalid RAG_QUERY_MODE: {env_rag_query_mode}")
        settings.rag_server.query_mode = env_rag_query_mode  # type: ignore[assignment]
    env_rag_python = os.getenv("RAG_SERVER_PYTHON")
    if env_rag_python:
        settings.rag_server.python_executable = env_rag_python
    env_rag_collection = os.getenv("RAG_COLLECTION")
    if env_rag_collection:
        settings.rag_server.collection = env_rag_collection
    env_database_url = os.getenv("DATABASE_URL")
    if env_database_url:
        settings.database.url = env_database_url
    env_service_token = os.getenv("AI_SERVICE_TOKEN")
    if env_service_token:
        settings.internal_api.service_token = SecretStr(env_service_token)
    env_execution_ttl = os.getenv("AI_EXECUTION_TTL_HOURS")
    if env_execution_ttl:
        settings.internal_api.execution_ttl_hours = int(env_execution_ttl)
    env_execution_database_url = os.getenv("AI_EXECUTION_DATABASE_URL")
    if env_execution_database_url:
        settings.internal_api.execution_database_url = env_execution_database_url
    env_shared_upload_root = os.getenv("SHARED_UPLOAD_ROOT")
    if env_shared_upload_root:
        settings.internal_api.shared_upload_root = env_shared_upload_root
    env_ingestion_worker_enabled = os.getenv("AI_INGESTION_WORKER_ENABLED")
    if env_ingestion_worker_enabled:
        settings.internal_api.ingestion_worker_enabled = env_ingestion_worker_enabled.lower() in {
            "1",
            "true",
            "yes",
        }
    env_legacy_measurement_enabled = os.getenv("LEGACY_MEASUREMENT_API_ENABLED")
    if env_legacy_measurement_enabled:
        settings.legacy_api.measurement_enabled = env_legacy_measurement_enabled.lower() in {
            "1",
            "true",
            "yes",
        }
    return settings


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate
