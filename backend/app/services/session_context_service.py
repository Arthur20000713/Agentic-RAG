from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from backend.app.schemas.agent import IntentType


SlotSource = Literal["user_confirmed", "ai_inferred", "missing", "stale", "tool_result"]
SPECIES_KEYWORDS = {
    "cattle": ("牛", "犊牛", "牦牛", "cattle", "calf", "cow", "yak"),
    "sheep": ("羊", "sheep"),
    "pig": ("猪", "pig"),
}
RESET_MARKERS = ("不是这头", "不是那头", "换一头", "换成", "另一头", "另外一头", "新问题", "重新开始")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionContextData(BaseModel):
    session_id: str
    last_intent: IntentType | None = None
    last_species: str | None = None
    last_symptoms: list[str] = Field(default_factory=list)
    last_animal_id: str | None = None
    pending_slots: list[str] = Field(default_factory=list)
    confirmed_case_fields: dict[str, Any] = Field(default_factory=dict)
    pending_questions: list[str] = Field(default_factory=list)
    answered_questions: list[str] = Field(default_factory=list)
    last_understanding: dict[str, Any] | None = None
    last_reasoning_result: dict[str, Any] | None = None
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    slot_sources: dict[str, SlotSource] = Field(default_factory=dict)
    risk_context_status: str = "empty"
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class SessionContextService:
    def __init__(self, conn: sqlite3.Connection, *, now_provider: Callable[[], datetime] = utc_now) -> None:
        self.conn = conn
        self.now_provider = now_provider

    def save_context(self, context: SessionContextData, *, status: str = "active") -> SessionContextData:
        now = self.now_provider()
        context = context.model_copy(update={"updated_at": now, "expires_at": context.expires_at or self._default_expires_at(context, now)})
        self.conn.execute(
            """
            INSERT INTO session_context (session_id, context_json, expires_at, status, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                context_json = excluded.context_json,
                expires_at = excluded.expires_at,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                context.session_id,
                json.dumps(context.model_dump(mode="json"), ensure_ascii=False),
                context.expires_at.isoformat() if context.expires_at else None,
                status,
                context.updated_at.isoformat(),
            ),
        )
        self.conn.commit()
        return context

    def get_context(self, session_id: str) -> SessionContextData | None:
        row = self._get_active_row(session_id)
        if row is None:
            return None
        context = SessionContextData.model_validate(json.loads(row["context_json"]))
        if self._is_expired(context):
            self.expire_stale_context(session_id)
            return None
        return context

    def update_context(self, session_id: str, **changes: Any) -> SessionContextData:
        current = self.get_context(session_id) or SessionContextData(session_id=session_id)
        data = current.model_dump()
        data.update(changes)
        updated = SessionContextData.model_validate(data)
        return self.save_context(updated)

    def set_slot_source(self, session_id: str, slot_name: str, source: SlotSource) -> SessionContextData:
        current = self.get_context(session_id) or SessionContextData(session_id=session_id)
        slot_sources = dict(current.slot_sources)
        slot_sources[slot_name] = source
        return self.update_context(session_id, slot_sources=slot_sources)

    def expire_stale_context(self, session_id: str) -> SessionContextData | None:
        row = self._get_active_row(session_id)
        if row is None:
            return None
        context = SessionContextData.model_validate(json.loads(row["context_json"]))
        stale_sources = {slot: "stale" for slot in context.slot_sources}
        stale_context = context.model_copy(
            update={
                "pending_slots": [],
                "slot_sources": stale_sources,
                "risk_context_status": "stale",
                "updated_at": self.now_provider(),
            }
        )
        self.save_context(stale_context, status="stale")
        return stale_context

    def clear_conflicted_context(self, session_id: str, query: str) -> bool:
        row = self._get_active_row(session_id)
        if row is None:
            return False
        context = SessionContextData.model_validate(json.loads(row["context_json"]))
        if not self._has_conflict(query, context):
            return False
        cleared = context.model_copy(
            update={
                "pending_slots": [],
                "slot_sources": {slot: "stale" for slot in context.slot_sources},
                "risk_context_status": "stale",
                "updated_at": self.now_provider(),
            }
        )
        self.save_context(cleared, status="cleared")
        return True

    def is_reusable_for_risk(self, context: SessionContextData) -> bool:
        if context.risk_context_status in {"high", "emergency"}:
            return False
        if context.slot_sources.get("risk_level") == "ai_inferred":
            return False
        return not self._is_expired(context)

    def _default_expires_at(self, context: SessionContextData, now: datetime) -> datetime:
        if context.last_intent == "disease_consultation" and context.pending_slots:
            return now + timedelta(hours=2)
        return now + timedelta(hours=24)

    def _is_expired(self, context: SessionContextData) -> bool:
        return context.expires_at is not None and context.expires_at <= self.now_provider()

    def _get_active_row(self, session_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT context_json FROM session_context
            WHERE session_id = ? AND status = 'active'
            """,
            (session_id,),
        ).fetchone()

    def _has_conflict(self, query: str, context: SessionContextData) -> bool:
        normalized = query.lower()
        if any(marker in normalized for marker in RESET_MARKERS):
            return True
        mentioned_species = self._mentioned_species(normalized)
        return context.last_species is not None and mentioned_species is not None and mentioned_species != context.last_species

    def _mentioned_species(self, normalized_query: str) -> str | None:
        for species, keywords in SPECIES_KEYWORDS.items():
            if any(keyword.lower() in normalized_query for keyword in keywords):
                return species
        return None
