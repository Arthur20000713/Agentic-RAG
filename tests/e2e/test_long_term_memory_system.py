from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.agent.checkpointing import checkpoint_database_path
from backend.app.agent.memory_store import memory_namespace
from backend.app.core.config import Settings
from backend.app.db.repositories import AgentTraceRepository
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.main import create_app


TOKEN = "memory-system-service-token-32-chars"
CHAT_PATH = "/internal/v1/ai/chat"


def _settings(database_url: str, *, read: bool = True, write: bool = True) -> Settings:
    return Settings(
        database={"url": database_url},
        internal_api={"service_token": TOKEN, "ingestion_worker_enabled": False},
        long_term_memory={"read_enabled": read, "write_enabled": write, "ttl_days": 365},
    )


def _app(settings: Settings):  # noqa: ANN202
    app = create_app(settings=settings)
    app.state.rag_client = FakeRagServerClient()
    return app


def _payload(
    *,
    suffix: str,
    conversation_id: str,
    query: str,
    user_id: str = "user_system",
) -> dict[str, Any]:
    return {
        "requestId": f"req_system_{suffix}",
        "operationId": f"op_system_{suffix}",
        "conversationId": conversation_id,
        "userId": user_id,
        "query": query,
        "animalSnapshot": {
            "animalId": "animal_system_001",
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


def _search_count(app, request_id: str) -> int:  # noqa: ANN001
    rows = AgentTraceRepository(app.state.execution_db_conn).list_by_request_id(request_id)
    trace = [item for row in rows for item in row["trace"]]
    node = next(item for item in trace if item.get("node") == "search_memory")
    return int(node["record_count"])


def test_memory_and_checkpoints_survive_app_restart_with_safety_boundaries(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'system-memory.db').as_posix()}"
    settings = _settings(database_url)

    first_app = _app(settings)
    with TestClient(first_app) as client:
        first = _post(
            client,
            _payload(
                suffix="0001",
                conversation_id="conversation_system_a",
                query="The calf has had diarrhea and reduced appetite for two days.",
            ),
        )
        assert first.status_code == 200
        assert "write_memory" in first.json()["toolsUsed"]

    checkpoint_path = Path(checkpoint_database_path(database_url))
    with sqlite3.connect(checkpoint_path) as checkpoint_db:
        checkpoint_count = checkpoint_db.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
    assert checkpoint_count > 0

    restarted_app = _app(settings)
    with TestClient(restarted_app) as client:
        recalled = _post(
            client,
            _payload(
                suffix="0002",
                conversation_id="conversation_system_b",
                query="The calf has no diarrhea today and is alert.",
            ),
        )
        isolated = _post(
            client,
            _payload(
                suffix="0003",
                conversation_id="conversation_system_c",
                user_id="other_system_user",
                query="The calf has no diarrhea today and is alert.",
            ),
        )

        assert recalled.status_code == isolated.status_code == 200
        assert "search_memory" in recalled.json()["toolsUsed"]
        assert _search_count(restarted_app, "req_system_0002") == 2
        assert _search_count(restarted_app, "req_system_0003") == 0
        assert recalled.json()["riskLevel"] not in {"HIGH", "CRITICAL"}
        assert "memory" not in str(recalled.json()["sources"]).casefold()
        assert len(
            restarted_app.state.memory_store.search(
                memory_namespace("user_system", "animal", "animal_system_001")
            )
        ) >= 2

    disabled_app = _app(_settings(database_url, read=False, write=False))
    with TestClient(disabled_app) as client:
        disabled = _post(
            client,
            _payload(
                suffix="0004",
                conversation_id="conversation_system_d",
                query="The calf has no diarrhea today and is alert.",
            ),
        )
        assert disabled.status_code == 200
        assert "search_memory" not in disabled.json()["toolsUsed"]
        assert "write_memory" not in disabled.json()["toolsUsed"]
