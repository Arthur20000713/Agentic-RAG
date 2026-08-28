from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from backend.app.agent.memory_store import memory_namespace
from backend.app.services.memory_service import MemorySource, MemorySubjectType


SEARCH_MEMORY_TOOL_NAME = "search_memory"
WRITE_MEMORY_TOOL_NAME = "write_memory"
MemoryType = Literal["animal_profile", "consultation", "measurement", "observation"]

_ALLOWED_MEMORY_TYPES = {"animal_profile", "consultation", "measurement", "observation"}
_ALLOWED_SOURCES = {"user_confirmed", "tool_result"}
_FORBIDDEN_CONTENT_KEYS = {
    "diagnosis",
    "diagnoses",
    "final_answer",
    "rag_summary",
    "recommendation",
    "recommendations",
    "risk_level",
    "treatment",
    "treatments",
}


class MemoryContextItem(BaseModel):
    record_id: str
    memory_type: MemoryType
    content: dict[str, Any]
    source: Literal["user_confirmed", "tool_result"]
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class MemoryWriteResult(BaseModel):
    status: Literal["written", "unchanged"]
    record: MemoryContextItem


async def write_memory(
    store: BaseStore,
    *,
    user_id: str,
    subject_type: MemorySubjectType,
    subject_id: str,
    memory_type: MemoryType,
    content: dict[str, Any],
    source: MemorySource,
    session_id: str | None = None,
    operation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ttl_days: int | None = None,
) -> MemoryWriteResult:
    """Write one trusted long-term memory record through the LangGraph Store."""

    _validate_write(memory_type, content, source, ttl_days)
    namespace = memory_namespace(user_id, subject_type, subject_id)
    record_id = _record_id(memory_type, operation_id)
    value = {
        "memory_type": memory_type,
        "content": dict(content),
        "source": source,
        "session_id": session_id,
        "metadata": dict(metadata or {}),
    }
    existing = await store.aget(namespace, record_id)
    if existing is not None and _same_memory(existing.value, value):
        return MemoryWriteResult(status="unchanged", record=_context_item(existing.value))

    ttl_minutes = None if ttl_days is None else ttl_days * 24 * 60
    await store.aput(namespace, record_id, value, ttl=ttl_minutes)
    saved = await store.aget(namespace, record_id)
    if saved is None:
        raise RuntimeError("memory store did not return the written record")
    return MemoryWriteResult(status="written", record=_context_item(saved.value))


async def search_memory(
    store: BaseStore,
    *,
    user_id: str,
    subject_type: MemorySubjectType,
    subject_id: str,
    query: str | None = None,
    memory_types: set[MemoryType] | None = None,
    limit: int = 5,
) -> list[MemoryContextItem]:
    """Search safe, non-expired memories inside one tenant/subject namespace."""

    if not 1 <= limit <= 20:
        raise ValueError("memory search limit must be between 1 and 20")
    if memory_types and not set(memory_types).issubset(_ALLOWED_MEMORY_TYPES):
        raise ValueError("memory search contains an unsupported memory_type")
    namespace = memory_namespace(user_id, subject_type, subject_id)
    candidates = await store.asearch(
        namespace,
        query=query,
        limit=min(100, max(20, limit * 4)),
    )
    results: list[MemoryContextItem] = []
    for candidate in candidates:
        value = candidate.value
        if value.get("source") not in _ALLOWED_SOURCES:
            continue
        memory_type = value.get("memory_type")
        if memory_type not in _ALLOWED_MEMORY_TYPES:
            continue
        if memory_types and memory_type not in memory_types:
            continue
        results.append(_context_item(value))
        if len(results) == limit:
            break
    return results


def _validate_write(
    memory_type: str,
    content: dict[str, Any],
    source: str,
    ttl_days: int | None,
) -> None:
    if memory_type not in _ALLOWED_MEMORY_TYPES:
        raise ValueError("unsupported memory_type")
    if source not in _ALLOWED_SOURCES:
        raise ValueError("memory source must be user_confirmed or tool_result")
    if not content:
        raise ValueError("memory content must not be empty")
    forbidden = _content_keys(content) & _FORBIDDEN_CONTENT_KEYS
    if forbidden:
        raise ValueError(f"memory content contains forbidden fields: {sorted(forbidden)}")
    if ttl_days is not None and ttl_days <= 0:
        raise ValueError("ttl_days must be positive")


def _content_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = {str(key).casefold() for key in value}
        for item in value.values():
            keys.update(_content_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(_content_keys(item))
        return keys
    return set()


def _record_id(memory_type: str, operation_id: str | None) -> str:
    if memory_type == "animal_profile":
        return "animal_profile"
    suffix = operation_id.strip() if operation_id and operation_id.strip() else uuid4().hex
    return f"{memory_type}:{suffix}"


def _same_memory(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(existing.get(key) == value for key, value in expected.items())


def _context_item(value: dict[str, Any]) -> MemoryContextItem:
    return MemoryContextItem.model_validate(value)


__all__ = [
    "MemoryContextItem",
    "MemoryType",
    "MemoryWriteResult",
    "SEARCH_MEMORY_TOOL_NAME",
    "WRITE_MEMORY_TOOL_NAME",
    "search_memory",
    "write_memory",
]
