from __future__ import annotations

import json
from typing import Any


def parse_local_json_response(text: str, schema_name: str) -> dict[str, Any]:
    normalized_schema = schema_name.strip().lower()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _schema_failure(normalized_schema, "response is not valid JSON", text)

    if not isinstance(payload, dict):
        return _schema_failure(normalized_schema, "response JSON must be an object", text)

    payload.setdefault("status", "success")
    payload.setdefault("schema_name", normalized_schema)
    payload.setdefault("fallback_required", False)
    return payload


def _schema_failure(schema_name: str, reason: str, raw_text: str) -> dict[str, Any]:
    return {
        "status": "error",
        "schema_name": schema_name,
        "fallback_required": True,
        "error_code": "LOCAL_MODEL_SCHEMA_ERROR",
        "reason": reason,
        "raw_text_preview": raw_text[:200],
    }
