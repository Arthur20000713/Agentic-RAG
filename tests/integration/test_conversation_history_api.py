from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import ConversationRepository, QaLogRepository
from backend.app.main import create_app


def _client() -> tuple[TestClient, sqlite3.Connection]:
    app = create_app(settings=Settings(database={"url": "sqlite:///:memory:"}))
    return TestClient(app), app.state.db_conn


def _chat(
    client: TestClient,
    query: str,
    session_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    body = {"query": query}
    if session_id is not None:
        body["session_id"] = session_id
    if user_id is not None:
        body["user_id"] = user_id
    payload = client.post("/api/chat", json=body).json()
    assert payload["code"] == 0
    return payload["data"]


def test_chat_creates_conversation_with_first_query_title_and_generated_session() -> None:
    client, _ = _client()

    first = _chat(client, "  hello   there  ")
    session_id = first["session_id"]
    _chat(client, "This later question must not replace the title", session_id)

    assert session_id.startswith("s_")
    detail = client.get(f"/api/conversations/{session_id}").json()["data"]
    assert detail["conversation"]["title"] == "hello there"
    assert detail["conversation"]["message_count"] == 4
    assert [message["role"] for message in detail["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert detail["messages"][0]["content"] == "hello   there"
    assert detail["messages"][2]["content"] == "This later question must not replace the title"


def test_conversation_list_is_sorted_by_update_time_and_searches_titles() -> None:
    client, conn = _client()
    _chat(client, "Calf feeding plan", "older")
    _chat(client, "羊羔断奶管理", "newer")
    conn.execute("UPDATE conversation SET updated_at = '2025-01-01 00:00:00' WHERE session_id = 'older'")
    conn.execute("UPDATE conversation SET updated_at = '2025-01-02 00:00:00' WHERE session_id = 'newer'")
    conn.commit()

    listed = client.get("/api/conversations").json()["data"]
    assert listed["total"] == 2
    assert [item["session_id"] for item in listed["items"]] == ["newer", "older"]
    assert listed["items"][0]["last_message_preview"]

    english = client.get("/api/conversations", params={"search": "FEEDING"}).json()["data"]
    assert english["total"] == 1
    assert english["items"][0]["session_id"] == "older"
    chinese = client.get("/api/conversations", params={"search": "断奶"}).json()["data"]
    assert chinese["total"] == 1
    assert chinese["items"][0]["session_id"] == "newer"


def test_conversation_can_be_renamed_and_deleted_with_related_history() -> None:
    client, conn = _client()
    _chat(client, "Original title", "managed")
    conn.execute(
        "INSERT INTO session_context (session_id, context_json) VALUES (?, ?)",
        ("managed", "{}"),
    )
    conn.execute(
        "INSERT INTO tool_call_log (session_id, tool_name) VALUES (?, ?)",
        ("managed", "test_tool"),
    )
    conn.commit()

    renamed = client.patch(
        "/api/conversations/managed",
        json={"title": "  My livestock notes  "},
    ).json()
    assert renamed["code"] == 0
    assert renamed["data"]["title"] == "My livestock notes"
    assert client.get("/api/conversations", params={"search": "livestock"}).json()["data"]["total"] == 1

    deleted = client.delete("/api/conversations/managed").json()
    assert deleted["code"] == 0
    assert deleted["data"] == {"session_id": "managed", "deleted": True}
    assert conn.execute("SELECT COUNT(*) FROM qa_log WHERE session_id = 'managed'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM session_context WHERE session_id = 'managed'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM tool_call_log WHERE session_id = 'managed'").fetchone()[0] == 0
    assert client.get("/api/conversations/managed").json()["code"] == 40004
    assert client.delete("/api/conversations/managed").json()["code"] == 40004


def test_conversation_title_is_concise_and_search_treats_wildcards_literally() -> None:
    client, _ = _client()
    long_query = "A" * 50
    _chat(client, long_query, "long")
    _chat(client, "100% feed plan", "percent")

    item = client.get("/api/conversations/long").json()["data"]["conversation"]
    assert item["title"] == f"{'A' * 39}…"
    assert len(item["title"]) == 40
    result = client.get("/api/conversations", params={"search": "%"}).json()["data"]
    assert result["total"] == 1
    assert result["items"][0]["session_id"] == "percent"


def test_init_db_backfills_conversation_metadata_from_legacy_qa_log() -> None:
    conn = get_connection("sqlite:///:memory:")
    conn.execute(
        """
        CREATE TABLE qa_log (
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
        )
        """
    )
    conn.execute(
        "INSERT INTO qa_log (session_id, user_query, final_answer, created_at) VALUES (?, ?, ?, ?)",
        ("legacy", "  Existing   user\nquestion  ", "Existing answer", "2024-01-01 00:00:00"),
    )
    conn.execute(
        "INSERT INTO qa_log (session_id, user_query, final_answer, created_at) VALUES (?, ?, ?, ?)",
        ("legacy", "Later question", "Later answer", "2024-01-02 00:00:00"),
    )
    init_db(conn)

    row = conn.execute("SELECT * FROM conversation WHERE session_id = 'legacy'").fetchone()
    assert row["title"] == "Existing user question"
    assert row["created_at"] == "2024-01-01 00:00:00"
    assert row["updated_at"] == "2024-01-02 00:00:00"
    assert row["owner_id"] == "legacy"
    conn.execute(
        "INSERT INTO qa_log (session_id, user_query, final_answer, created_at) VALUES (?, ?, ?, ?)",
        ("legacy", "Newest question", "Newest answer", "2024-01-03 00:00:00"),
    )
    init_db(conn)
    refreshed = conn.execute("SELECT * FROM conversation WHERE session_id = 'legacy'").fetchone()
    assert refreshed["title"] == "Existing user question"
    assert refreshed["updated_at"] == "2024-01-03 00:00:00"


def test_conversations_are_isolated_by_client_and_legacy_is_not_anonymous() -> None:
    client, conn = _client()
    _chat(client, "Owner one private question", "shared_name", "owner.one")

    assert client.get("/api/conversations").json()["data"]["total"] == 0
    owner_headers = {"X-Client-ID": "owner.one"}
    assert client.get("/api/conversations", headers=owner_headers).json()["data"]["total"] == 1
    assert client.get("/api/conversations/shared_name").json()["code"] == 40004
    assert client.get("/api/conversations/shared_name", headers=owner_headers).json()["code"] == 0
    assert client.patch(
        "/api/conversations/shared_name", json={"title": "stolen"}
    ).json()["code"] == 40004
    assert client.delete("/api/conversations/shared_name").json()["code"] == 40004

    collision = client.post(
        "/api/chat",
        json={"query": "try collision", "session_id": "shared_name", "user_id": "owner.two"},
    ).json()
    assert collision["code"] == 40300
    assert conn.execute("SELECT COUNT(*) FROM qa_log WHERE session_id = 'shared_name'").fetchone()[0] == 1


def test_list_supports_pagination_and_searches_message_content() -> None:
    client, conn = _client()
    _chat(client, "First title", "first")
    _chat(client, "Second title", "second")
    client.patch("/api/conversations/second", json={"title": "Renamed conversation"})

    page = client.get("/api/conversations", params={"limit": 1, "offset": 1}).json()["data"]
    assert page["total"] == 2
    assert page["limit"] == 1
    assert page["offset"] == 1
    assert len(page["items"]) == 1
    message_search = client.get(
        "/api/conversations", params={"search": "Second title"}
    ).json()["data"]
    assert message_search["total"] == 1
    assert message_search["items"][0]["session_id"] == "second"
    conn.execute(
        "UPDATE qa_log SET final_answer = 'assistant-only-search-needle' WHERE session_id = 'first'"
    )
    conn.commit()
    answer_search = client.get(
        "/api/conversations", params={"search": "only-search-needle"}
    ).json()["data"]
    assert answer_search["total"] == 1
    assert answer_search["items"][0]["session_id"] == "first"


def test_detail_restores_complete_assistant_snapshot_without_raw_chunk_content() -> None:
    client, conn = _client()
    _chat(client, "hello", "snapshot")
    row = conn.execute(
        "SELECT response_json FROM qa_log WHERE session_id = 'snapshot'"
    ).fetchone()
    assert row["response_json"] is not None

    assistant = client.get("/api/conversations/snapshot").json()["data"]["messages"][1]
    assert set(
        (
            "content",
            "intent",
            "risk_level",
            "sources",
            "tools_used",
            "need_follow_up",
            "follow_up_questions",
            "errors",
        )
    ).issubset(assistant)

    conn.execute(
        "UPDATE qa_log SET response_json = NULL, retrieved_chunks = ? WHERE session_id = 'snapshot'",
        ('[{"title":"Guide","chunk_id":"c1","content":"secret raw passage"}]',),
    )
    conn.commit()
    legacy_assistant = client.get("/api/conversations/snapshot").json()["data"]["messages"][1]
    assert legacy_assistant["sources"] == [{"title": "Guide", "chunk_id": "c1"}]
    assert "secret raw passage" not in str(legacy_assistant)


def test_init_db_upgrades_intermediate_conversation_table_idempotently() -> None:
    conn = get_connection("sqlite:///:memory:")
    conn.executescript(
        """
        CREATE TABLE qa_log (
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
        CREATE TABLE conversation (
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO conversation (session_id, title) VALUES ('intermediate', 'Kept title');
        """
    )

    init_db(conn)
    init_db(conn)

    row = conn.execute("SELECT * FROM conversation WHERE session_id = 'intermediate'").fetchone()
    assert row["title"] == "Kept title"
    assert row["owner_id"] == "legacy"
    indexes = {row["name"] for row in conn.execute("PRAGMA index_list(conversation)").fetchall()}
    assert "idx_conversation_owner_updated_at" in indexes


def test_detail_orders_turns_by_timestamp_then_id() -> None:
    client, conn = _client()
    _chat(client, "Inserted first", "chronological")
    _chat(client, "Inserted second", "chronological")
    rows = conn.execute(
        "SELECT id FROM qa_log WHERE session_id = 'chronological' ORDER BY id"
    ).fetchall()
    conn.execute("UPDATE qa_log SET created_at = '2025-01-02' WHERE id = ?", (rows[0]["id"],))
    conn.execute("UPDATE qa_log SET created_at = '2025-01-01' WHERE id = ?", (rows[1]["id"],))
    conn.commit()

    messages = client.get("/api/conversations/chronological").json()["data"]["messages"]
    assert messages[0]["content"] == "Inserted second"
    assert messages[2]["content"] == "Inserted first"


def test_conversation_api_validates_identifiers_paging_and_titles() -> None:
    client, _ = _client()

    assert client.post(
        "/api/chat", json={"query": "hello", "session_id": "bad/session"}
    ).json()["code"] == 40001
    assert client.post(
        "/api/chat", json={"query": "hello", "user_id": "bad user"}
    ).json()["code"] == 40001
    assert client.get("/api/conversations", params={"limit": 0}).json()["code"] == 40001
    assert client.get(
        "/api/conversations", headers={"X-Client-ID": "bad/client"}
    ).json()["code"] == 40001

    _chat(client, "Valid conversation", "valid")
    assert client.patch(
        "/api/conversations/valid", json={"title": f"  {'x' * 80}  "}
    ).json()["code"] == 0
    assert client.patch(
        "/api/conversations/valid", json={"title": "x" * 81}
    ).json()["code"] == 40001
    assert client.patch(
        "/api/conversations/valid", json={"title": "   "}
    ).json()["code"] == 40001


def test_conversation_and_qa_turn_can_rollback_as_one_transaction() -> None:
    _, conn = _client()
    conversations = ConversationRepository(conn)
    qa_logs = QaLogRepository(conn)

    with pytest.raises(TypeError):
        conversations.record_turn("atomic", "owner", "Atomic title", commit=False)
        qa_logs.add(
            session_id="atomic",
            user_query="Atomic title",
            intent="out_of_scope",
            final_answer="answer",
            response_data={"not_json": object()},
            commit=False,
        )
    conn.rollback()

    assert conversations.get("atomic", "owner") is None
    assert conn.execute("SELECT COUNT(*) FROM qa_log WHERE session_id = 'atomic'").fetchone()[0] == 0
