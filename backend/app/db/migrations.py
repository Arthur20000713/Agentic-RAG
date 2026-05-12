from __future__ import annotations

import sqlite3


APPLICATION_TABLES = {
    "farm_profile",
    "animal_profile",
    "body_measurement_record",
    "rag_ingestion_task",
    "qa_log",
    "tool_call_log",
    "agent_trace_log",
    "rag_trace_log",
    "session_context",
    "eval_run_log",
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

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
    latency_ms INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_trace_request_id
ON rag_trace_log(request_id);

CREATE INDEX IF NOT EXISTS idx_rag_trace_session_id
ON rag_trace_log(session_id);

CREATE TABLE IF NOT EXISTS session_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    context_json TEXT NOT NULL,
    expires_at TEXT,
    status TEXT DEFAULT 'active',
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
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
