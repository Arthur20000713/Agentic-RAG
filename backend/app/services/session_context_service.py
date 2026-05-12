from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field

from backend.app.schemas.agent import IntentType


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionContextData(BaseModel):
    session_id: str
    last_intent: IntentType | None = None
    last_species: str | None = None
    last_symptoms: list[str] = Field(default_factory=list)
    last_animal_id: str | None = None
    pending_slots: list[str] = Field(default_factory=list)
    slot_sources: dict[str, str] = Field(default_factory=dict)
    risk_context_status: str = "empty"
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class SessionContextService:
    def __init__(self, conn: sqlite3.Connection, *, now_provider: Callable[[], datetime] = utc_now) -> None:
        self.conn = conn
        self.now_provider = now_provider

    def save_context(self, context: SessionContextData, *, status: str = "active") -> SessionContextData:
        context = context.model_copy(update={"updated_at": self.now_provider()})
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
        row = self.conn.execute(
            """
            SELECT context_json FROM session_context
            WHERE session_id = ? AND status = 'active'
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return SessionContextData.model_validate(json.loads(row["context_json"]))

    def update_context(self, session_id: str, **changes: Any) -> SessionContextData:
        current = self.get_context(session_id) or SessionContextData(session_id=session_id)
        updated = current.model_copy(update=changes)
        return self.save_context(updated)
