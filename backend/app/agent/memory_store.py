from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

from backend.app.db.repositories import MemoryRepository
from backend.app.services.memory_service import MemoryEvent, MemorySubjectType


MEMORY_NAMESPACE = "memory"
_ALLOWED_SOURCES = {"user_confirmed", "tool_result"}
_GENERATED_FIELDS = {
    "created_at",
    "event_id",
    "expires_at",
    "record_id",
    "subject_id",
    "subject_type",
    "updated_at",
    "user_id",
}


class RepositoryMemoryStore(BaseStore):
    """LangGraph Store adapter over the existing append-only memory repository."""

    supports_ttl = True

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        with self._lock:
            return [self._execute(op) for op in ops]

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        return await asyncio.to_thread(self.batch, list(ops))

    def _execute(self, op: Op) -> Result:
        if isinstance(op, GetOp):
            return self._get(op.namespace, op.key)
        if isinstance(op, PutOp):
            self._put(op)
            return None
        if isinstance(op, SearchOp):
            return self._search(op)
        if isinstance(op, ListNamespacesOp):
            return self._list_namespaces(op)
        raise TypeError(f"unsupported store operation: {type(op).__name__}")

    def _get(self, namespace: tuple[str, ...], key: str) -> Item | None:
        user_id, subject_type, subject_id = _parse_namespace(namespace)
        projection = self.repository.get_projection(
            subject_type,
            _scoped_subject_id(user_id, subject_id),
        )
        value = projection.get(key)
        if not isinstance(value, dict) or _is_expired(value, self._clock()):
            return None
        return _item(namespace, key, value)

    def _put(self, op: PutOp) -> None:
        user_id, subject_type, subject_id = _parse_namespace(op.namespace)
        scoped_id = _scoped_subject_id(user_id, subject_id)
        projection = self.repository.get_projection(subject_type, scoped_id)
        existing = projection.get(op.key)
        if op.value is None:
            if isinstance(existing, dict):
                self.repository.delete_fact(
                    subject_type=subject_type,
                    subject_id=scoped_id,
                    fact_type=op.key,
                    source="user_confirmed",
                    supersedes_event_id=_optional_text(existing.get("event_id")),
                )
            return

        source = op.value.get("source")
        if source not in _ALLOWED_SOURCES:
            raise ValueError("memory source must be user_confirmed or tool_result")
        if isinstance(existing, dict) and _business_value(existing) == _business_value(dict(op.value)):
            return

        now = self._clock()
        event_id = f"mem_{uuid4().hex}"
        expires_at = (
            now + timedelta(minutes=op.ttl)
            if op.ttl is not None
            else _parse_optional_datetime(op.value.get("expires_at"))
        )
        created_at = (
            _parse_datetime(existing.get("created_at"))
            if isinstance(existing, dict)
            else now
        )
        record = {
            **dict(op.value),
            "record_id": op.key,
            "event_id": event_id,
            "user_id": user_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "created_at": created_at.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
        }
        event = MemoryEvent(
            event_id=event_id,
            subject_type=subject_type,
            subject_id=scoped_id,
            event_type="supersede" if isinstance(existing, dict) else "upsert",
            source=source,
            payload={
                "fact_type": op.key,
                "value": record,
                "metadata": dict(op.value.get("metadata") or {}),
            },
            supersedes_event_id=(
                _optional_text(existing.get("event_id"))
                if isinstance(existing, dict)
                else None
            ),
        )
        self.repository.append_event(event)

    def _search(self, op: SearchOp) -> list[SearchItem]:
        namespaces = self._namespaces(op.namespace_prefix)
        results: list[SearchItem] = []
        now = self._clock()
        for namespace in namespaces:
            user_id, subject_type, subject_id = _parse_namespace(namespace)
            projection = self.repository.get_projection(
                subject_type,
                _scoped_subject_id(user_id, subject_id),
            )
            for key, value in projection.items():
                if not isinstance(value, dict) or _is_expired(value, now):
                    continue
                if op.filter and not _matches_filter(value, op.filter):
                    continue
                score = _query_score(value, op.query)
                if op.query and score == 0:
                    continue
                item = _item(namespace, key, value)
                results.append(
                    SearchItem(
                        namespace=item.namespace,
                        key=item.key,
                        value=item.value,
                        created_at=item.created_at,
                        updated_at=item.updated_at,
                        score=score if op.query else None,
                    )
                )
        results.sort(
            key=lambda item: (item.score or 0, item.updated_at, item.key),
            reverse=True,
        )
        return results[op.offset : op.offset + op.limit]

    def _list_namespaces(self, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        namespaces = self._namespaces((MEMORY_NAMESPACE,))
        for condition in op.match_conditions or ():
            namespaces = [
                namespace
                for namespace in namespaces
                if _matches_namespace_condition(namespace, condition.match_type, condition.path)
            ]
        if op.max_depth is not None:
            namespaces = [namespace[: op.max_depth] for namespace in namespaces]
        unique = sorted(set(namespaces))
        return unique[op.offset : op.offset + op.limit]

    def _namespaces(self, prefix: tuple[str, ...]) -> list[tuple[str, ...]]:
        if not prefix or prefix[0] != MEMORY_NAMESPACE:
            return []
        if len(prefix) == 1:
            candidates = self._all_namespaces()
        elif len(prefix) < 4:
            candidates = self._all_namespaces(user_id=prefix[1])
        else:
            _parse_namespace(prefix)
            candidates = [prefix]
        return [namespace for namespace in candidates if namespace[: len(prefix)] == prefix]

    def _all_namespaces(self, user_id: str | None = None) -> list[tuple[str, ...]]:
        namespaces: list[tuple[str, ...]] = []
        for subject_type, table_name, key_column in (
            ("animal", "animal_memory", "animal_id"),
            ("farm", "farm_memory", "farm_id"),
        ):
            rows = self.repository.conn.execute(
                f"SELECT {key_column} AS scoped_id FROM {table_name}"
            ).fetchall()
            for row in rows:
                decoded = _decode_scoped_subject_id(str(row["scoped_id"]))
                if decoded is None:
                    continue
                owner, subject_id = decoded
                if user_id is None or owner == user_id:
                    namespaces.append((MEMORY_NAMESPACE, owner, subject_type, subject_id))
        return namespaces


def memory_namespace(
    user_id: str,
    subject_type: MemorySubjectType,
    subject_id: str,
) -> tuple[str, ...]:
    namespace = (MEMORY_NAMESPACE, user_id.strip(), subject_type, subject_id.strip())
    _parse_namespace(namespace)
    return namespace


def _parse_namespace(
    namespace: tuple[str, ...],
) -> tuple[str, MemorySubjectType, str]:
    if len(namespace) != 4 or namespace[0] != MEMORY_NAMESPACE:
        raise ValueError("memory namespace must be (memory, user_id, subject_type, subject_id)")
    _, user_id, subject_type, subject_id = namespace
    if not user_id or not subject_id or subject_type not in {"animal", "farm"}:
        raise ValueError("memory namespace contains an invalid identity")
    return user_id, subject_type, subject_id  # type: ignore[return-value]


def _scoped_subject_id(user_id: str, subject_id: str) -> str:
    return json.dumps([user_id, subject_id], ensure_ascii=False, separators=(",", ":"))


def _decode_scoped_subject_id(value: str) -> tuple[str, str] | None:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(decoded, list)
        or len(decoded) != 2
        or not all(isinstance(item, str) and item for item in decoded)
    ):
        return None
    return decoded[0], decoded[1]


def _item(namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> Item:
    return Item(
        namespace=namespace,
        key=key,
        value=value,
        created_at=_parse_datetime(value.get("created_at")),
        updated_at=_parse_datetime(value.get("updated_at")),
    )


def _business_value(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in _GENERATED_FIELDS}


def _parse_datetime(value: Any) -> datetime:
    parsed = _parse_optional_datetime(value)
    if parsed is None:
        raise ValueError("memory record is missing a valid timestamp")
    return parsed


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        raise ValueError("memory timestamp must be an ISO datetime")
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _is_expired(value: dict[str, Any], now: datetime) -> bool:
    expires_at = _parse_optional_datetime(value.get("expires_at"))
    return expires_at is not None and expires_at <= now


def _matches_filter(value: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(value.get(key) == item for key, item in expected.items())


def _query_score(value: dict[str, Any], query: str | None) -> float:
    if not query or not query.strip():
        return 0.0
    haystack = json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()
    terms = [term for term in query.casefold().split() if term]
    if not terms:
        return 0.0
    return sum(term in haystack for term in terms) / len(terms)


def _matches_namespace_condition(
    namespace: tuple[str, ...],
    match_type: str,
    path: tuple[str, ...],
) -> bool:
    if len(path) > len(namespace):
        return False
    values = namespace[: len(path)] if match_type == "prefix" else namespace[-len(path) :]
    return all(expected == "*" or expected == actual for expected, actual in zip(path, values))


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = ["MEMORY_NAMESPACE", "RepositoryMemoryStore", "memory_namespace"]
