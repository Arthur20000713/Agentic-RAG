from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from backend.app.services.memory_service import MemoryEvent, MemorySource, MemorySubjectType


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

    def recent(self, session_id: str, *, limit: int = 6) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT user_query, final_answer, intent
            FROM qa_log
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, max(1, limit)),
        ).fetchall()
        return [
            {
                "user": row["user_query"],
                "assistant": row["final_answer"],
                "intent": row["intent"],
            }
            for row in reversed(rows)
        ]


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


class AgentTraceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
        trace: list[dict[str, Any]] | dict[str, Any],
        status: str,
        latency_ms: int | None = None,
        error_code: str | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO agent_trace_log (
                session_id, request_id, trace_json, status, latency_ms, error_code
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                request_id,
                json.dumps(trace, ensure_ascii=False),
                status,
                latency_ms,
                error_code,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def get(self, trace_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM agent_trace_log WHERE id = ?",
            (trace_id,),
        ).fetchone()
        return None if row is None else self._decode(row)

    def list_by_request_id(self, request_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM agent_trace_log
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            (request_id,),
        ).fetchall()
        return [self._decode(row) for row in rows]

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["trace"] = json.loads(data.pop("trace_json"))
        return data


class RagTraceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
        rag_mode: str,
        collection: str | None = None,
        query: str | None = None,
        top_k: int | None = None,
        result_count: int | None = None,
        mapped_result_count: int | None = None,
        top_score: float | None = None,
        raw_response_id: str | None = None,
        status: str,
        error_code: str | None = None,
        attempt_count: int = 1,
        latency_ms: int | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO rag_trace_log (
                session_id, request_id, rag_mode, collection, query, top_k,
                result_count, mapped_result_count, top_score, raw_response_id,
                status, error_code, attempt_count, latency_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                request_id,
                rag_mode,
                collection,
                query,
                top_k,
                result_count,
                mapped_result_count,
                top_score,
                raw_response_id,
                status,
                error_code,
                attempt_count,
                latency_ms,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def get(self, trace_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM rag_trace_log WHERE id = ?",
            (trace_id,),
        ).fetchone()
        return None if row is None else dict(row)

    def list_by_request_id(self, request_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM rag_trace_log
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            (request_id,),
        ).fetchall()
        return [dict(row) for row in rows]


class ModelRouteLogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(
        self,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
        route_request: Any,
        route_decision: Any,
    ) -> int:
        request_data = self._as_dict(route_request)
        decision_data = self._as_dict(route_decision)
        cursor = self.conn.execute(
            """
            INSERT INTO model_route_log (
                session_id, request_id, task_type, safety_level, selected_model,
                route_mode, shadow_model, local_candidate_allowed, blocked_reason,
                reason, fallback_required, fallback_reason, latency_ms, model_version,
                route_request_json, route_decision_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                request_id,
                request_data.get("task_type"),
                request_data.get("safety_level"),
                decision_data.get("selected_model"),
                decision_data.get("route_mode"),
                decision_data.get("shadow_model"),
                1 if decision_data.get("local_candidate_allowed") else 0,
                decision_data.get("blocked_reason"),
                decision_data.get("reason"),
                1 if decision_data.get("fallback_required") else 0,
                decision_data.get("fallback_reason"),
                decision_data.get("latency_ms"),
                decision_data.get("model_version"),
                json.dumps(request_data, ensure_ascii=False),
                json.dumps(decision_data, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add(
        self,
        *,
        session_id: str | None = None,
        request_id: str | None = None,
        route_request: Any,
        route_decision: Any,
    ) -> int:
        return self.create(
            session_id=session_id,
            request_id=request_id,
            route_request=route_request,
            route_decision=route_decision,
        )

    def get(self, log_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM model_route_log WHERE id = ?",
            (log_id,),
        ).fetchone()
        return None if row is None else self._decode(row)

    def list_by_request_id(self, request_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM model_route_log
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            (request_id,),
        ).fetchall()
        return [self._decode(row) for row in rows]

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["local_candidate_allowed"] = bool(data["local_candidate_allowed"])
        data["fallback_required"] = bool(data.get("fallback_required"))
        data["route_request"] = json.loads(data.pop("route_request_json"))
        data["route_decision"] = json.loads(data.pop("route_decision_json"))
        return data

    def _as_dict(self, value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        return dict(value)


class MemoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def append_event(self, event: MemoryEvent) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO memory_event (
                event_id, subject_type, subject_id, event_type, source,
                payload_json, supersedes_event_id, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                event.event_id,
                event.subject_type,
                event.subject_id,
                event.event_type,
                event.source,
                json.dumps(event.payload, ensure_ascii=False),
                event.supersedes_event_id,
            ),
        )
        self._apply_projection(event)
        self.conn.commit()
        return int(cursor.lastrowid)

    def supersede_fact(
        self,
        *,
        subject_type: MemorySubjectType,
        subject_id: str,
        fact_type: str,
        value: Any,
        source: MemorySource,
        supersedes_event_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        event = MemoryEvent(
            event_id=f"mem_{uuid4().hex}",
            subject_type=subject_type,
            subject_id=subject_id,
            event_type="supersede",
            source=source,
            payload={"fact_type": fact_type, "value": value, "metadata": metadata or {}},
            supersedes_event_id=supersedes_event_id,
        )
        self.append_event(event)
        return event

    def delete_fact(
        self,
        *,
        subject_type: MemorySubjectType,
        subject_id: str,
        fact_type: str,
        source: MemorySource,
        supersedes_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        event = MemoryEvent(
            event_id=f"mem_{uuid4().hex}",
            subject_type=subject_type,
            subject_id=subject_id,
            event_type="delete",
            source=source,
            payload={"fact_type": fact_type, "value": None, "metadata": metadata or {}},
            supersedes_event_id=supersedes_event_id,
        )
        self.append_event(event)
        return event

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM memory_event WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data

    def get_projection(self, subject_type: MemorySubjectType, subject_id: str) -> dict[str, Any]:
        table_name, key_column = self._projection_table(subject_type)
        row = self.conn.execute(
            f"SELECT memory_json FROM {table_name} WHERE {key_column} = ?",
            (subject_id,),
        ).fetchone()
        if row is None:
            return {}
        return json.loads(row["memory_json"])

    def _apply_projection(self, event: MemoryEvent) -> None:
        fact_type = event.payload.get("fact_type")
        if not isinstance(fact_type, str) or not fact_type:
            raise ValueError("memory event payload must include fact_type")

        projection = self.get_projection(event.subject_type, event.subject_id)
        if event.event_type == "delete":
            projection.pop(fact_type, None)
        else:
            projection[fact_type] = event.payload.get("value")

        table_name, key_column = self._projection_table(event.subject_type)
        self.conn.execute(
            f"""
            INSERT INTO {table_name} ({key_column}, memory_json, updated_event_id)
            VALUES (?, ?, ?)
            ON CONFLICT({key_column}) DO UPDATE SET
                memory_json = excluded.memory_json,
                updated_event_id = excluded.updated_event_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                event.subject_id,
                json.dumps(projection, ensure_ascii=False),
                event.event_id,
            ),
        )

    def _projection_table(self, subject_type: MemorySubjectType) -> tuple[str, str]:
        if subject_type == "farm":
            return "farm_memory", "farm_id"
        if subject_type == "animal":
            return "animal_memory", "animal_id"
        raise ValueError(f"unsupported memory subject_type: {subject_type}")


class EvalRunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(
        self,
        *,
        run_id: str,
        eval_type: str,
        rag_mode: str,
        total_cases: int,
        passed_cases: int,
        metrics: dict[str, Any] | None = None,
        failure_summary: dict[str, Any] | None = None,
        report_path: str | None = None,
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO eval_run_log (
                run_id, eval_type, rag_mode, total_cases, passed_cases,
                metrics_json, failure_summary_json, report_path
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                eval_type,
                rag_mode,
                total_cases,
                passed_cases,
                json.dumps(metrics or {}, ensure_ascii=False),
                json.dumps(failure_summary or {}, ensure_ascii=False),
                report_path,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def get(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM eval_run_log WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["metrics"] = json.loads(data.pop("metrics_json") or "{}")
        data["failure_summary"] = json.loads(data.pop("failure_summary_json") or "{}")
        return data
