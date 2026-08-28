from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.agent.memory_store import memory_namespace
from backend.app.core.config import Settings
from backend.app.db.repositories import AgentTraceRepository
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.main import create_app


TOKEN = "memory-internal-service-token-32-chars"
CHAT_PATH = "/internal/v1/ai/chat"


def _payload(
    *,
    request_id: str,
    operation_id: str,
    conversation_id: str,
    user_id: str = "user_memory",
    query: str = "犊牛腹泻两天，精神差",
) -> dict[str, Any]:
    return {
        "requestId": request_id,
        "operationId": operation_id,
        "conversationId": conversation_id,
        "userId": user_id,
        "query": query,
        "animalSnapshot": {
            "animalId": "animal_memory_001",
            "species": "cattle",
            "breed": "Holstein",
            "attributes": {},
        },
        "history": [],
        "context": {"schemaVersion": 1, "slots": {}},
        "contextVersion": 0,
        "deadlineMs": 60000,
    }


def _post(client: TestClient, payload: dict[str, Any]) -> Any:
    return client.post(
        CHAT_PATH,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "X-Request-ID": payload["requestId"],
            "Idempotency-Key": f"idem_{payload['operationId']}",
        },
        json=payload,
    )


def _memory_trace_count(app, request_id: str) -> int:  # noqa: ANN001
    rows = AgentTraceRepository(app.state.execution_db_conn).list_by_request_id(request_id)
    nodes = [item for row in rows for item in row["trace"]]
    search = next(item for item in nodes if item.get("node") == "search_memory")
    return int(search["record_count"])


def test_internal_chat_reads_memory_across_conversations_and_isolates_user(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'memory-api.db').as_posix()}"
    settings = Settings(
        database={"url": database_url},
        internal_api={"service_token": TOKEN, "ingestion_worker_enabled": False},
        long_term_memory={"read_enabled": True, "write_enabled": True, "ttl_days": 365},
    )
    app = create_app(settings=settings)
    app.state.rag_client = FakeRagServerClient()

    with TestClient(app) as client:
        first = _post(
            client,
            _payload(
                request_id="req_memory_0001",
                operation_id="op_memory_0001",
                conversation_id="conv_memory_0001",
            ),
        )
        second = _post(
            client,
            _payload(
                request_id="req_memory_0002",
                operation_id="op_memory_0002",
                conversation_id="conv_memory_0002",
                query="今天仍然没有好转",
            ),
        )
        isolated = _post(
            client,
            _payload(
                request_id="req_memory_0003",
                operation_id="op_memory_0003",
                conversation_id="conv_memory_0003",
                user_id="other_user",
                query="今天仍然没有好转",
            ),
        )

        assert first.status_code == second.status_code == isolated.status_code == 200
        assert "write_memory" in first.json()["toolsUsed"]
        assert "search_memory" in second.json()["toolsUsed"]
        assert _memory_trace_count(app, "req_memory_0002") == 2
        assert _memory_trace_count(app, "req_memory_0003") == 0
        assert len(
            app.state.memory_store.search(
                memory_namespace("user_memory", "animal", "animal_memory_001")
            )
        ) == 2
