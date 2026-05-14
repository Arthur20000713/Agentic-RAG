from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.response import ApiResponse
from backend.app.services.feature_flag_service import FeatureFlagService


router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("/{request_id}")
async def get_trace_bundle(request: Request, request_id: str) -> dict:
    agent_trace = request.app.state.trace_service.list_agent_traces(request_id)
    return ApiResponse.ok(
        {
            "request_id": request_id,
            "agent_trace": agent_trace,
            "tool_trace": [],
            "rag_trace": [],
            "safety_result": None,
            "verifier_result": None,
            "v3_debug_summary": v3_debug_summary(request, request_id, agent_trace),
        }
    ).model_dump()


def v3_debug_summary(request: Request, request_id: str, agent_trace: list[dict]) -> dict:
    flags = FeatureFlagService(request.app.state.settings).snapshot().model_dump()
    trace_items = _flatten_agent_trace(agent_trace)
    return {
        "request_id": request_id,
        "flags": flags,
        "route": _route_summary(trace_items),
        "safety": _safety_summary(trace_items),
        "memory": _memory_summary(request, flags),
        "agent_path": [str(item.get("node")) for item in trace_items if item.get("node")],
    }


def _flatten_agent_trace(agent_trace: list[dict]) -> list[dict]:
    items: list[dict] = []
    for row in agent_trace:
        trace = row.get("trace")
        if isinstance(trace, list):
            items.extend(item for item in trace if isinstance(item, dict))
        elif isinstance(trace, dict):
            items.append(trace)
    return items


def _route_summary(trace_items: list[dict]) -> dict:
    route_nodes = [
        item
        for item in trace_items
        if item.get("node") in {"model_router_shadow", "disease_slot_router", "measurement_json_renderer"}
    ]
    if not route_nodes:
        return {"status": "not_available"}
    latest = route_nodes[-1]
    return {
        "status": latest.get("status", "unknown"),
        "route_mode": latest.get("route_mode"),
        "selected_model": latest.get("selected_model"),
        "shadow_model": latest.get("shadow_model"),
        "safety_level": latest.get("safety_level"),
        "local_candidate_allowed": latest.get("local_candidate_allowed"),
    }


def _safety_summary(trace_items: list[dict]) -> dict:
    safety_nodes = [item for item in trace_items if item.get("node") == "safety_agent"]
    if not safety_nodes:
        return {"status": "not_available"}
    latest = safety_nodes[-1]
    return {
        "status": latest.get("status"),
        "passed": latest.get("passed"),
        "violation_count": latest.get("violation_count", 0),
        "hard_blocked": latest.get("hard_blocked", False),
        "violations": latest.get("violations", []),
    }


def _memory_summary(request: Request, flags: dict) -> dict:
    row = request.app.state.db_conn.execute("SELECT COUNT(*) AS count FROM memory_event").fetchone()
    return {
        "write_enabled": flags["memory_write_enabled"],
        "read_enabled": flags["memory_read_enabled"],
        "event_count": int(row["count"] if row is not None else 0),
    }
