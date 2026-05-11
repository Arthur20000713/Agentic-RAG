from __future__ import annotations

from backend.app.core.errors import AppError, ErrorCode
from backend.app.core.response import ApiResponse


def test_success_response_contract() -> None:
    response = ApiResponse.ok({"answer": "ok"}, request_id="req_test")

    assert response.model_dump() == {
        "code": 0,
        "message": "success",
        "data": {"answer": "ok"},
        "request_id": "req_test",
    }


def test_error_response_contract() -> None:
    error = AppError(ErrorCode.RAG_SERVER_UNAVAILABLE, "rag server unavailable")
    response = ApiResponse.from_error(error, request_id="req_error")

    assert response.code == 50002
    assert response.message == "rag server unavailable"
    assert response.data == {}
    assert response.request_id == "req_error"

