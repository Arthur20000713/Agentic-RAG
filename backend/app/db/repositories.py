from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class AnimalRecord:
    animal_id: str
    farm_id: str | None = None
    species: str | None = None
    breed: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    note: str | None = None


class AnimalRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, record: AnimalRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO animal_profile
                (animal_id, farm_id, species, breed, gender, birth_date, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(animal_id) DO UPDATE SET
                farm_id = excluded.farm_id,
                species = excluded.species,
                breed = excluded.breed,
                gender = excluded.gender,
                birth_date = excluded.birth_date,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                record.animal_id,
                record.farm_id,
                record.species,
                record.breed,
                record.gender,
                record.birth_date,
                record.note,
            ),
        )
        self.conn.commit()


class MeasurementRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        *,
        animal_id: str,
        measure_date: date | str,
        values: dict[str, float | None],
        source: str | None = None,
        confidence: float | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO body_measurement_record (
                animal_id, measure_date, body_height_cm, body_length_cm,
                chest_girth_cm, chest_depth_cm, chest_width_cm, weight_kg,
                source, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                animal_id,
                str(measure_date),
                values.get("body_height_cm"),
                values.get("body_length_cm"),
                values.get("chest_girth_cm"),
                values.get("chest_depth_cm"),
                values.get("chest_width_cm"),
                values.get("weight_kg"),
                source,
                confidence,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_history(self, animal_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT measure_date, body_height_cm, body_length_cm, chest_girth_cm,
                   chest_depth_cm, chest_width_cm, weight_kg, source, confidence
            FROM body_measurement_record
            WHERE animal_id = ?
            ORDER BY measure_date DESC
            LIMIT ?
            """,
            (animal_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


class RagIngestionTaskRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, task_id: str, document_path: str, collection: str = "default") -> None:
        self.conn.execute(
            """
            INSERT INTO rag_ingestion_task (task_id, document_path, collection)
            VALUES (?, ?, ?)
            """,
            (task_id, document_path, collection),
        )
        self.conn.commit()

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM rag_ingestion_task WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def update_status(
        self,
        task_id: str,
        status: str,
        *,
        error_message: str | None = None,
        chunk_count: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE rag_ingestion_task
            SET status = ?,
                error_message = ?,
                chunk_count = COALESCE(?, chunk_count),
                started_at = CASE WHEN ? = 'running' THEN CURRENT_TIMESTAMP ELSE started_at END,
                finished_at = CASE WHEN ? = 'success' THEN CURRENT_TIMESTAMP ELSE finished_at END,
                failed_at = CASE WHEN ? = 'failed' THEN CURRENT_TIMESTAMP ELSE failed_at END
            WHERE task_id = ?
            """,
            (status, error_message, chunk_count, status, status, status, task_id),
        )
        self.conn.commit()


class QaLogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        *,
        session_id: str | None,
        user_query: str,
        intent: str | None,
        final_answer: str,
        tools_used: list[str] | None = None,
        retrieved_chunks: list[dict[str, Any]] | None = None,
        risk_level: str | None = None,
        latency_ms: int | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO qa_log (
                session_id, user_query, intent, tools_used, retrieved_chunks,
                final_answer, risk_level, latency_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user_query,
                intent,
                json.dumps(tools_used or [], ensure_ascii=False),
                json.dumps(retrieved_chunks or [], ensure_ascii=False),
                final_answer,
                risk_level,
                latency_ms,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)


class ToolCallLogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        *,
        session_id: str | None,
        tool_name: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any] | None,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        latency_ms: int | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO tool_call_log (
                session_id, tool_name, input, output, status,
                error_code, error_message, latency_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                tool_name,
                json.dumps(input_data, ensure_ascii=False),
                json.dumps(output_data or {}, ensure_ascii=False),
                status,
                error_code,
                error_message,
                latency_ms,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

