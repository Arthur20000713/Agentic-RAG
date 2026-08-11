from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.core.internal_api import canonical_request_hash
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient
from backend.app.main import create_app
from backend.app.schemas.internal_v1 import ChatRequest, ChatRun, ErrorDetail
from backend.app.services.internal_ai_service import InternalAiService


SERVICE_TOKEN = "test-java-service-token-32-characters"
CHAT_PATH = "/internal/v1/ai/chat"
MEASUREMENT_PATH = "/internal/v1/ai/measurements/analyze"


class CountingFakeRagServerClient(FakeRagServerClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_count = 0

    async def query(self, *args: Any, **kwargs: Any):  # noqa: ANN201
        self.query_count += 1
        return await super().query(*args, **kwargs)


def _client() -> tuple[TestClient, Any]:
    settings = Settings(
        database={"url": "sqlite:///:memory:"},
        internal_api={"service_token": SERVICE_TOKEN},
    )
    app = create_app(settings=settings)
    return TestClient(app), app


def _headers(
    request_id: str,
    *,
    idempotency_key: str | None = None,
    token: str | None = SERVICE_TOKEN,
) -> dict[str, str]:
    headers = {"X-Request-ID": request_id}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _chat_payload(
    *,
    request_id: str = "req_chat_0001",
    operation_id: str = "op_chat_0001",
    query: str = "How should cattle feeding be managed?",
) -> dict[str, Any]:
    return {
        "requestId": request_id,
        "operationId": operation_id,
        "conversationId": "conv_chat_0001",
        "userId": "user_chat_0001",
        "query": query,
        "animalSnapshot": {
            "animalId": "animal_chat_0001",
            "species": "cattle",
        },
        "history": [],
        "context": {
            "schemaVersion": 1,
            "slots": {},
            "forwardCompatibleField": {"keep": True},
        },
        "contextVersion": 0,
        "deadlineMs": 60000,
    }


def _post_chat(
    client: TestClient,
    payload: dict[str, Any],
    *,
    idempotency_key: str = "idem_chat_0001",
):
    return client.post(
        CHAT_PATH,
        headers=_headers(payload["requestId"], idempotency_key=idempotency_key),
        json=payload,
    )


def _assert_request_id_echo(response, expected: str) -> None:  # noqa: ANN001
    assert response.headers["X-Request-ID"] == expected
    assert response.json()["requestId"] == expected


def test_internal_business_endpoint_requires_service_bearer() -> None:
    client, _app = _client()
    payload = _chat_payload()

    response = client.post(
        CHAT_PATH,
        headers=_headers(
            payload["requestId"],
            idempotency_key="idem_chat_auth_0001",
            token=None,
        ),
        json=payload,
    )

    assert response.status_code == 401
    _assert_request_id_echo(response, payload["requestId"])
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "SERVICE_UNAUTHORIZED"
    assert response.json()["error"]["retryable"] is False


def test_internal_business_endpoint_accepts_case_insensitive_bearer_scheme() -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_lower_bearer_0001",
        operation_id="op_chat_lower_bearer_0001",
    )
    headers = _headers(
        payload["requestId"],
        idempotency_key="idem_chat_lower_bearer_0001",
    )
    headers["Authorization"] = f"bearer {SERVICE_TOKEN}"

    response = client.post(CHAT_PATH, headers=headers, json=payload)

    assert response.status_code == 200
    _assert_request_id_echo(response, payload["requestId"])


def test_internal_chat_requires_contract_deadline() -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_deadline_0001",
        operation_id="op_chat_deadline_0001",
    )
    payload.pop("deadlineMs")

    response = _post_chat(
        client,
        payload,
        idempotency_key="idem_chat_deadline_0001",
    )

    assert response.status_code == 422
    _assert_request_id_echo(response, payload["requestId"])
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


def test_internal_chat_rejects_deadline_above_java_contract() -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_long_deadline_0001",
        operation_id="op_chat_long_deadline_0001",
    )
    payload["deadlineMs"] = 60001

    response = _post_chat(
        client,
        payload,
        idempotency_key="idem_chat_long_deadline_0001",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("RUNNING", ErrorDetail(code="INVALID", message="must be absent", retryable=False)),
        ("SUCCEEDED", None),
        ("FAILED", None),
    ],
)
def test_chat_run_rejects_status_payload_mismatch(status: str, error: ErrorDetail | None) -> None:
    now = datetime.now(timezone.utc)

    with pytest.raises(ValidationError):
        ChatRun(
            request_id="req_chat_run_invalid_0001",
            operation_id="op_chat_run_invalid_0001",
            run_id="run_chat_invalid_0001",
            status=status,
            result=None,
            error=error,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=1),
        )


def test_internal_chat_returns_contract_response_with_grounded_sources() -> None:
    client, app = _client()
    payload = _chat_payload()

    response = _post_chat(client, payload)

    assert response.status_code == 200
    _assert_request_id_echo(response, payload["requestId"])
    body = response.json()
    assert body["operationId"] == payload["operationId"]
    assert body["outcome"] == "ANSWERED"
    assert body["answer"]
    assert body["intent"] == "general_qa"
    assert body["riskLevel"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert body["evidenceStatus"] == "SUPPORTED"
    assert body["sources"]
    assert body["contextVersion"] == payload["contextVersion"] + 1
    assert body["nextContext"]["forwardCompatibleField"] == {"keep": True}
    assert body["runId"]
    assert body["traceId"]
    assert set(body["safety"]) == {"decision", "reasonCode"}
    for source in body["sources"]:
        assert {
            "collection",
            "documentId",
            "title",
            "chunkId",
            "score",
        } <= set(source)
        assert 0 <= source["score"] <= 1
    assert app.state.db_conn.execute("SELECT COUNT(*) FROM conversation").fetchone()[0] == 0
    assert app.state.db_conn.execute("SELECT COUNT(*) FROM qa_log").fetchone()[0] == 0
    assert app.state.db_conn.execute("SELECT COUNT(*) FROM session_context").fetchone()[0] == 0


def test_internal_chat_low_confidence_has_no_citations() -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_low_0001",
        operation_id="op_chat_low_0001",
        query="low confidence livestock question",
    )

    response = _post_chat(client, payload, idempotency_key="idem_chat_low_0001")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "LOW_CONFIDENCE"
    assert body["evidenceStatus"] == "LOW_CONFIDENCE"
    assert body["sources"] == []


def test_internal_chat_maps_policy_block_to_safety_refusal() -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_safety_0001",
        operation_id="op_chat_safety_0001",
        query="A sick cattle has fever. Give an exact prescription and drug dosage.",
    )

    response = _post_chat(client, payload, idempotency_key="idem_chat_safety_0001")

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "disease_consultation"
    assert body["outcome"] == "SAFETY_REFUSAL"
    assert body["safety"]["decision"] == "REFUSED"
    assert body["sources"] == []


def test_internal_chat_returns_structured_follow_up_from_opaque_context() -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_followup_0001",
        operation_id="op_chat_followup_0001",
        query="A sick cattle has fever.",
    )
    payload["context"]["slots"] = {
        "pending_questions": ["How long has the fever lasted?"],
    }

    response = _post_chat(client, payload, idempotency_key="idem_chat_followup_0001")

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "NEEDS_FOLLOW_UP"
    assert body["followUpQuestions"] == ["How long has the fever lasted?"]
    assert body["nextContext"]["slots"]["pending_questions"] == body["followUpQuestions"]


def test_internal_chat_rejects_request_id_header_body_mismatch() -> None:
    client, _app = _client()
    payload = _chat_payload(request_id="req_chat_body_0001")

    response = client.post(
        CHAT_PATH,
        headers=_headers(
            "req_chat_header_0001",
            idempotency_key="idem_chat_mismatch_0001",
        ),
        json=payload,
    )

    assert response.status_code == 400
    _assert_request_id_echo(response, "req_chat_header_0001")
    assert response.json()["error"]["code"] == "REQUEST_ID_MISMATCH"


def test_internal_chat_rejects_invalid_request_id_and_blank_query() -> None:
    client, _app = _client()
    invalid_id_payload = _chat_payload(request_id="req_valid_0001")
    invalid_id = client.post(
        CHAT_PATH,
        headers=_headers("invalid!!", idempotency_key="idem_invalid_id_0001"),
        json=invalid_id_payload,
    )
    blank_payload = _chat_payload(
        request_id="req_blank_query_0001",
        operation_id="op_blank_query_0001",
        query="   ",
    )
    blank = _post_chat(client, blank_payload, idempotency_key="idem_blank_query_0001")

    assert invalid_id.status_code == 400
    assert invalid_id.json()["error"]["code"] == "INVALID_REQUEST"
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


def test_internal_chat_returns_422_for_schema_validation_error() -> None:
    client, _app = _client()
    payload = _chat_payload(request_id="req_chat_schema_0001")
    payload.pop("query")

    response = client.post(
        CHAT_PATH,
        headers=_headers(
            payload["requestId"],
            idempotency_key="idem_chat_schema_0001",
        ),
        json=payload,
    )

    assert response.status_code == 422
    _assert_request_id_echo(response, payload["requestId"])
    body = response.json()
    assert body["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert body["error"]["retryable"] is False
    assert "traceback" not in response.text.lower()


def test_same_chat_operation_and_payload_replays_persisted_result() -> None:
    client, app = _client()
    counting_rag = CountingFakeRagServerClient()
    app.state.rag_client = counting_rag
    payload = _chat_payload(
        request_id="req_chat_replay_0001",
        operation_id="op_chat_replay_0001",
    )

    first = _post_chat(client, payload, idempotency_key="idem_chat_replay_0001")
    second = _post_chat(client, payload, idempotency_key="idem_chat_replay_0001")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert counting_rag.query_count == 1


def test_failed_chat_replay_preserves_original_timeout_status(monkeypatch) -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_timeout_0001",
        operation_id="op_chat_timeout_0001",
    )

    async def timeout_chat(self, payload, *, run_id):  # noqa: ANN001, ANN202, ARG001
        raise asyncio.TimeoutError

    monkeypatch.setattr(InternalAiService, "chat", timeout_chat)
    first = _post_chat(client, payload, idempotency_key="idem_chat_timeout_0001")
    replay = _post_chat(client, payload, idempotency_key="idem_chat_timeout_0001")

    assert first.status_code == 504
    assert replay.status_code == 504
    assert first.json()["error"]["code"] == "DEADLINE_EXCEEDED"
    assert replay.json()["error"]["code"] == "DEADLINE_EXCEEDED"


def test_failed_chat_replay_preserves_retryable_guidance(monkeypatch) -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_failure_replay_0001",
        operation_id="op_chat_failure_replay_0001",
    )

    async def failed_chat(self, payload, *, run_id):  # noqa: ANN001, ANN202, ARG001
        raise RuntimeError("simulated AI failure")

    monkeypatch.setattr(InternalAiService, "chat", failed_chat)
    first = _post_chat(client, payload, idempotency_key="idem_chat_failure_replay_0001")
    replay = _post_chat(client, payload, idempotency_key="idem_chat_failure_replay_0001")

    assert first.status_code == replay.status_code == 503
    assert first.json()["error"] == replay.json()["error"]
    assert first.json()["error"]["retryable"] is True


def test_active_running_replay_is_not_taken_over() -> None:
    client, app = _client()
    counting_rag = CountingFakeRagServerClient()
    app.state.rag_client = counting_rag
    payload = _chat_payload(
        request_id="req_chat_active_lease_0001",
        operation_id="op_chat_active_lease_0001",
    )
    request_hash = canonical_request_hash(
        "AI_CHAT",
        ChatRequest.model_validate(payload).model_dump(mode="json", by_alias=True),
    )
    app.state.ai_execution_repository.claim(
        operation_id=payload["operationId"],
        idempotency_key="idem_chat_active_lease_0001",
        operation_type="AI_CHAT",
        request_id=payload["requestId"],
        request_hash=request_hash,
    )

    response = _post_chat(
        client,
        payload,
        idempotency_key="idem_chat_active_lease_0001",
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "CONCURRENCY_LIMITED"
    assert counting_rag.query_count == 0


def test_stale_running_replay_is_recovered_to_single_success() -> None:
    client, app = _client()
    counting_rag = CountingFakeRagServerClient()
    app.state.rag_client = counting_rag
    payload = _chat_payload(
        request_id="req_chat_stale_lease_0001",
        operation_id="op_chat_stale_lease_0001",
    )
    request_hash = canonical_request_hash(
        "AI_CHAT",
        ChatRequest.model_validate(payload).model_dump(mode="json", by_alias=True),
    )
    claim = app.state.ai_execution_repository.claim(
        operation_id=payload["operationId"],
        idempotency_key="idem_chat_stale_lease_0001",
        operation_type="AI_CHAT",
        request_id=payload["requestId"],
        request_hash=request_hash,
    )
    stale_at = "2000-01-01T00:00:00+00:00"
    app.state.execution_db_conn.execute(
        "UPDATE ai_execution_record SET updated_at = ? WHERE operation_id = ?",
        (stale_at, payload["operationId"]),
    )
    app.state.execution_db_conn.commit()

    recovered = _post_chat(
        client,
        payload,
        idempotency_key="idem_chat_stale_lease_0001",
    )
    replay = _post_chat(
        client,
        payload,
        idempotency_key="idem_chat_stale_lease_0001",
    )

    assert claim.record is not None
    assert recovered.status_code == replay.status_code == 200
    assert recovered.json() == replay.json()
    assert recovered.json()["runId"] == claim.record["run_id"]
    assert counting_rag.query_count == 1


@pytest.mark.parametrize("terminal_method", ["complete", "fail"])
def test_execution_terminal_store_failure_returns_contract_503(
    monkeypatch,
    terminal_method: str,
) -> None:
    client, app = _client()
    payload = _chat_payload(
        request_id=f"req_chat_store_{terminal_method}_0001",
        operation_id=f"op_chat_store_{terminal_method}_0001",
    )

    if terminal_method == "fail":
        async def failed_chat(self, payload, *, run_id):  # noqa: ANN001, ANN202, ARG001
            raise RuntimeError("simulated AI failure")

        monkeypatch.setattr(InternalAiService, "chat", failed_chat)

    def fail_store(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise OSError("simulated execution store failure")

    monkeypatch.setattr(
        app.state.ai_execution_repository,
        terminal_method,
        fail_store,
    )

    response = _post_chat(
        client,
        payload,
        idempotency_key=f"idem_chat_store_{terminal_method}_0001",
    )

    assert response.status_code == 503
    _assert_request_id_echo(response, payload["requestId"])
    assert response.json()["operationId"] == payload["operationId"]
    assert response.json()["error"]["code"] == "EXECUTION_STORE_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True


@pytest.mark.parametrize(
    ("second_operation_id", "second_idempotency_key"),
    [
        ("op_chat_conflict_0001", "idem_chat_conflict_new_0001"),
        ("op_chat_conflict_new_0001", "idem_chat_conflict_0001"),
    ],
)
def test_reusing_operation_or_idempotency_key_for_different_request_returns_409(
    second_operation_id: str,
    second_idempotency_key: str,
) -> None:
    client, _app = _client()
    first_payload = _chat_payload(
        request_id="req_chat_conflict_0001",
        operation_id="op_chat_conflict_0001",
    )
    second_payload = deepcopy(first_payload)
    second_payload.update(
        {
            "operationId": second_operation_id,
            "query": "A materially different livestock question",
        }
    )

    first = _post_chat(
        client,
        first_payload,
        idempotency_key="idem_chat_conflict_0001",
    )
    second = _post_chat(
        client,
        second_payload,
        idempotency_key=second_idempotency_key,
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert second.json()["operationId"] == second_operation_id


def test_get_chat_run_returns_persisted_successful_result() -> None:
    client, _app = _client()
    payload = _chat_payload(
        request_id="req_chat_run_0001",
        operation_id="op_chat_run_0001",
    )
    created = _post_chat(client, payload, idempotency_key="idem_chat_run_0001")
    lookup_request_id = "req_chat_lookup_0001"

    response = client.get(
        f"/internal/v1/ai/runs/{payload['operationId']}",
        headers=_headers(lookup_request_id),
    )

    assert created.status_code == 200
    assert response.status_code == 200
    _assert_request_id_echo(response, lookup_request_id)
    body = response.json()
    assert body["operationId"] == payload["operationId"]
    assert body["type"] == "AI_CHAT"
    assert body["status"] == "SUCCEEDED"
    assert body["result"] == created.json()
    assert body["error"] is None
    assert body["expiresAt"]


def test_internal_measurement_uses_history_supplied_in_request() -> None:
    client, _app = _client()
    request_id = "req_measurement_0001"
    payload = {
        "requestId": request_id,
        "operationId": "op_measurement_0001",
        "userId": "user_measurement_0001",
        "animalSnapshot": {
            "animalId": "animal_measurement_0001",
            "species": "cattle",
        },
        "ageMonth": 18,
        "current": {
            "chestGirthCm": 121.0,
            "weightKg": 205.0,
        },
        "history": [
            {
                "measureDate": "2026-07-01",
                "chestGirthCm": 120.0,
                "weightKg": 203.0,
            }
        ],
        "confidence": 0.95,
        "useDemoHistory": False,
        "deadlineMs": 10000,
    }

    response = client.post(
        MEASUREMENT_PATH,
        headers=_headers(request_id, idempotency_key="idem_measurement_0001"),
        json=payload,
    )

    assert response.status_code == 200
    _assert_request_id_echo(response, request_id)
    body = response.json()
    assert body["operationId"] == payload["operationId"]
    assert body["outcome"] == "ANALYZED"
    assert body["result"]["animalId"] == payload["animalSnapshot"]["animalId"]
    assert body["result"]["usedDemoHistory"] is False
    evidence = "\n".join(body["result"]["evidence"])
    assert "120.0" in evidence
    assert "121.0" in evidence


def test_internal_measurement_history_requires_a_measurement_value() -> None:
    client, _app = _client()
    request_id = "req_measurement_empty_history_0001"
    payload = {
        "requestId": request_id,
        "operationId": "op_measurement_empty_history_0001",
        "userId": "user_measurement_0001",
        "animalSnapshot": {
            "animalId": "animal_measurement_0001",
            "species": "cattle",
        },
        "current": {"weightKg": 205.0},
        "history": [{"measureDate": "2026-07-01"}],
        "deadlineMs": 10000,
    }

    response = client.post(
        MEASUREMENT_PATH,
        headers=_headers(request_id, idempotency_key="idem_measurement_empty_history_0001"),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


def test_internal_liveness_and_readiness_have_real_http_semantics() -> None:
    client, _app = _client()

    liveness = client.get("/internal/v1/health/liveness")
    readiness = client.get("/internal/v1/health/readiness")

    assert liveness.status_code == 200
    assert liveness.json()["status"] == "UP"
    assert liveness.json()["requestId"] == liveness.headers["X-Request-ID"]

    readiness_body = readiness.json()
    expected_status = 200 if readiness_body["status"] == "READY" else 503
    assert readiness.status_code == expected_status
    assert readiness_body["checks"]
    assert readiness_body["requestId"] == readiness.headers["X-Request-ID"]
