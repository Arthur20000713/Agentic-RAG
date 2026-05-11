from __future__ import annotations

from backend.app.db.connection import get_connection
from backend.app.db.migrations import init_db
from backend.app.db.repositories import (
    QaLogRepository,
    RagIngestionTaskRepository,
    ToolCallLogRepository,
)


def test_task_and_log_repositories_write_and_read() -> None:
    conn = get_connection("sqlite:///:memory:")
    init_db(conn)

    tasks = RagIngestionTaskRepository(conn)
    tasks.create("task_1", "docs/a.pdf", "default")
    tasks.update_status("task_1", "success", chunk_count=3)

    assert tasks.get("task_1")["status"] == "success"
    assert tasks.get("task_1")["chunk_count"] == 3

    qa_id = QaLogRepository(conn).add(
        session_id="s1",
        user_query="q",
        intent="general_qa",
        final_answer="answer",
        tools_used=["livestock_rag_search"],
    )
    tool_id = ToolCallLogRepository(conn).add(
        session_id="s1",
        tool_name="livestock_rag_search",
        input_data={"query": "q"},
        output_data={"status": "success"},
        status="success",
        latency_ms=10,
    )

    assert qa_id > 0
    assert tool_id > 0

