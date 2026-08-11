from __future__ import annotations

import sqlite3


APPLICATION_TABLES = {
    "farm_profile",
    "animal_profile",
    "body_measurement_record",
    "rag_ingestion_task",
    "qa_log",
    "conversation",
    "tool_call_log",
    "agent_trace_log",
    "rag_trace_log",
    "model_route_log",
    "session_context",
    "memory_event",
    "farm_memory",
    "animal_memory",
    "eval_run_log",
    "ai_execution_record",
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS farm_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id TEXT UNIQUE NOT NULL,
    name TEXT,
    location TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS animal_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id TEXT UNIQUE NOT NULL,
    farm_id TEXT REFERENCES farm_profile(farm_id),
    species TEXT,
    breed TEXT,
    gender TEXT,
    birth_date TEXT,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_animal_farm_id ON animal_profile(farm_id);

CREATE TABLE IF NOT EXISTS body_measurement_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id TEXT NOT NULL REFERENCES animal_profile(animal_id),
    measure_date TEXT NOT NULL,
    body_height_cm REAL,
    body_length_cm REAL,
    chest_girth_cm REAL,
    chest_depth_cm REAL,
    chest_width_cm REAL,
    weight_kg REAL,
    source TEXT,
    confidence REAL,
    algorithm_version TEXT,
    measurement_batch_id TEXT,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_measurement_animal_date
ON body_measurement_record(animal_id, measure_date);

CREATE TABLE IF NOT EXISTS rag_ingestion_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    document_path TEXT NOT NULL,
    collection TEXT DEFAULT 'default',
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    failed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS qa_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    user_query TEXT NOT NULL,
    intent TEXT,
    tools_used TEXT,
    retrieved_chunks TEXT,
    final_answer TEXT,
    risk_level TEXT,
    latency_ms INTEGER,
    response_json TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_qa_log_session_id_id
ON qa_log(session_id, id);

CREATE INDEX IF NOT EXISTS idx_qa_log_session_created_at
ON qa_log(session_id, created_at, id);

CREATE TABLE IF NOT EXISTS conversation (
    session_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversation_updated_at
ON conversation(updated_at DESC);

CREATE TABLE IF NOT EXISTS tool_call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    tool_name TEXT NOT NULL,
    input TEXT,
    output TEXT,
    status TEXT,
    error_code TEXT,
    error_message TEXT,
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_trace_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    request_id TEXT,
    trace_json TEXT NOT NULL,
    status TEXT,
    latency_ms INTEGER,
    error_code TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_trace_request_id
ON agent_trace_log(request_id);

CREATE INDEX IF NOT EXISTS idx_agent_trace_session_id
ON agent_trace_log(session_id);

CREATE TABLE IF NOT EXISTS rag_trace_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    request_id TEXT,
    rag_mode TEXT,
    collection TEXT,
    query TEXT,
    top_k INTEGER,
    result_count INTEGER,
    mapped_result_count INTEGER,
    top_score REAL,
    raw_response_id TEXT,
    status TEXT,
    error_code TEXT,
    attempt_count INTEGER DEFAULT 1,
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_trace_request_id
ON rag_trace_log(request_id);

CREATE INDEX IF NOT EXISTS idx_rag_trace_session_id
ON rag_trace_log(session_id);

CREATE TABLE IF NOT EXISTS model_route_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    request_id TEXT,
    task_type TEXT NOT NULL,
    safety_level TEXT,
    selected_model TEXT NOT NULL,
    route_mode TEXT NOT NULL,
    shadow_model TEXT,
    local_candidate_allowed INTEGER DEFAULT 0,
    blocked_reason TEXT,
    reason TEXT,
    fallback_required INTEGER DEFAULT 0,
    fallback_reason TEXT,
    latency_ms INTEGER,
    model_version TEXT,
    route_request_json TEXT NOT NULL,
    route_decision_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_model_route_log_request_id
ON model_route_log(request_id);

CREATE INDEX IF NOT EXISTS idx_model_route_log_session_id
ON model_route_log(session_id);

CREATE TABLE IF NOT EXISTS session_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    context_json TEXT NOT NULL,
    expires_at TEXT,
    status TEXT DEFAULT 'active',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    supersedes_event_id TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_memory_event_subject
ON memory_event(subject_type, subject_id);

CREATE INDEX IF NOT EXISTS idx_memory_event_supersedes
ON memory_event(supersedes_event_id);

CREATE TABLE IF NOT EXISTS farm_memory (
    farm_id TEXT PRIMARY KEY,
    memory_json TEXT NOT NULL,
    updated_event_id TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS animal_memory (
    animal_id TEXT PRIMARY KEY,
    memory_json TEXT NOT NULL,
    updated_event_id TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    eval_type TEXT,
    rag_mode TEXT,
    total_cases INTEGER,
    passed_cases INTEGER,
    metrics_json TEXT,
    failure_summary_json TEXT,
    report_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_execution_record (
    operation_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    operation_type TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    request_json TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_execution_status_updated
ON ai_execution_record(status, updated_at);

CREATE INDEX IF NOT EXISTS idx_ai_execution_expires_at
ON ai_execution_record(expires_at);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    _ensure_column(conn, "qa_log", "response_json", "TEXT")
    _ensure_column(conn, "conversation", "owner_id", "TEXT NOT NULL DEFAULT 'legacy'")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_owner_updated_at "
        "ON conversation(owner_id, updated_at DESC)"
    )
    _ensure_column(conn, "rag_trace_log", "attempt_count", "INTEGER DEFAULT 1")
    _ensure_column(conn, "model_route_log", "fallback_required", "INTEGER DEFAULT 0")
    _ensure_column(conn, "model_route_log", "fallback_reason", "TEXT")
    _ensure_column(conn, "model_route_log", "latency_ms", "INTEGER")
    _ensure_column(conn, "model_route_log", "model_version", "TEXT")
    _ensure_column(conn, "ai_execution_record", "request_json", "TEXT")
    _ensure_column(conn, "ai_execution_record", "lease_token", "TEXT")
    _ensure_column(conn, "ai_execution_record", "lease_expires_at", "TEXT")
    _ensure_column(conn, "ai_execution_record", "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    _backfill_conversations(conn)
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _backfill_conversations(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT grouped.session_id,
               (SELECT first.user_query
                FROM qa_log AS first
                WHERE first.session_id = grouped.session_id
                ORDER BY first.id ASC
                LIMIT 1) AS first_query,
               grouped.created_at,
               grouped.updated_at
        FROM (
            SELECT session_id, MIN(created_at) AS created_at, MAX(created_at) AS updated_at
            FROM qa_log
            WHERE session_id IS NOT NULL AND TRIM(session_id) != ''
            GROUP BY session_id
        ) AS grouped
        """
    ).fetchall()
    values = [
        (
            row["session_id"],
            _conversation_title(row["first_query"]),
            row["created_at"],
            row["updated_at"],
        )
        for row in rows
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO conversation (session_id, owner_id, title, created_at, updated_at)
        VALUES (?, 'legacy', ?, ?, ?)
        """,
        values,
    )
    conn.executemany(
        """
        UPDATE conversation
        SET created_at = CASE WHEN created_at IS NULL OR created_at > ? THEN ? ELSE created_at END,
            updated_at = CASE WHEN updated_at IS NULL OR updated_at < ? THEN ? ELSE updated_at END
        WHERE session_id = ? AND owner_id = 'legacy'
        """,
        [
            (created_at, created_at, updated_at, updated_at, session_id)
            for session_id, _title, created_at, updated_at in values
        ],
    )


def _conversation_title(query: str, *, max_length: int = 40) -> str:
    normalized = " ".join(query.split()) or "新对话"
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 1].rstrip()}…"
