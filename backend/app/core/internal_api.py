from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import Header, Request


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


@dataclass(frozen=True)
class InternalApiError(Exception):
    status_code: int
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)
    operation_id: str | None = None


def request_id_or_new(request: Request) -> str:
    value = request.headers.get("X-Request-ID")
    return value if value and REQUEST_ID_PATTERN.fullmatch(value) else f"req_{uuid4().hex}"


async def require_service_bearer(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    configured = request.app.state.settings.internal_api.service_token
    if configured is None or not configured.get_secret_value():
        raise InternalApiError(
            503,
            "AI_SERVICE_UNAVAILABLE",
            "internal service authentication is not configured",
            retryable=False,
        )
    if authorization is None:
        raise InternalApiError(
            401,
            "SERVICE_UNAUTHORIZED",
            "valid service bearer token is required",
        )
    scheme, separator, credentials = authorization.partition(" ")
    candidate = credentials.strip()
    if separator != " " or scheme.lower() != "bearer":
        raise InternalApiError(
            401,
            "SERVICE_UNAUTHORIZED",
            "valid service bearer token is required",
        )
    if not candidate or not secrets.compare_digest(candidate, configured.get_secret_value()):
        raise InternalApiError(
            401,
            "SERVICE_UNAUTHORIZED",
            "valid service bearer token is required",
        )


def require_request_id(value: str | None) -> str:
    if value is None or REQUEST_ID_PATTERN.fullmatch(value) is None:
        raise InternalApiError(
            400,
            "INVALID_REQUEST",
            "X-Request-ID is required",
        )
    return value


def require_matching_request_id(header_value: str, body_value: str, *, operation_id: str) -> None:
    if header_value != body_value:
        raise InternalApiError(
            400,
            "REQUEST_ID_MISMATCH",
            "X-Request-ID must match requestId",
            operation_id=operation_id,
        )


def canonical_request_hash(operation_type: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"type": operation_type, "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
