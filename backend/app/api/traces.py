from __future__ import annotations

from fastapi import APIRouter, Request

from backend.app.core.response import ApiResponse
from backend.app.services.chat_service import build_rag_status_payload
from backend.app.services.feature_flag_service import FeatureFlagService

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("/{request_id}")
async def get_trace_bundle(request: Request, request_id: str) -> dict:
    agent_trace = request.app.state.trace_service.list_agent_traces(request_id)
    rag_trace = request.app.state.trace_service.list_rag_traces(request_id)
    trace_items = _flatten_agent_trace(agent_trace)
    safety_summary = _safety_summary(trace_items)
    verifier_summary = _verifier_summary(trace_items)
    return ApiResponse.ok(
        {
            "request_id": request_id,
            "agent_trace": agent_trace,
            "tool_trace": [],
            "rag_trace": rag_trace,
            "safety_result": None if safety_summary["status"] == "not_available" else safety_summary,
            "verifier_result": None if verifier_summary["status"] == "not_available" else verifier_summary,
            "agent_runtime_debug_summary": agent_runtime_debug_summary(request, request_id, agent_trace),
        }
    ).model_dump()


def agent_runtime_debug_summary(request: Request, request_id: str, agent_trace: list[dict]) -> dict:
    flags = FeatureFlagService(request.app.state.settings).snapshot().model_dump()
    trace_items = _flatten_agent_trace(agent_trace)
    return {
        "request_id": request_id,
        "engine": flags["agent_runtime_engine"],
        "flags": flags,
        "route": _route_summary(trace_items),
        "safety": _safety_summary(trace_items),
        "planning": _planning_summary(trace_items),
        "model_usage": _model_usage_summary(trace_items),
        "memory": _memory_summary(request, flags),
        "rag_status": build_rag_status_payload(request.app.state.settings),
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
        if item.get("node") in {"model_router_shadow", "measurement_json_renderer"}
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


def _verifier_summary(trace_items: list[dict]) -> dict:
    verifier_nodes = [item for item in trace_items if item.get("node") == "verifier_agent"]
    if not verifier_nodes:
        return {"status": "not_available"}
    latest = verifier_nodes[-1]
    return {
        "status": latest.get("status"),
        "passed": latest.get("passed"),
        "issue_count": latest.get("issue_count", 0),
        "citation_issue_count": latest.get("citation_issue_count", 0),
        "unsupported_claim_count": latest.get("unsupported_claim_count", 0),
    }


def _planning_summary(trace_items: list[dict]) -> dict:
    planner_items = [item for item in trace_items if item.get("node") == "planner"]
    if not planner_items:
        return {"status": "not_available"}

    planner = planner_items[-1]
    executor_items = [item for item in trace_items if item.get("node") == "executor"]
    verifier_items = [item for item in trace_items if item.get("node") == "plan_verifier"]
    replan_items = [item for item in trace_items if item.get("node") == "replan"]
    latest_verifier = verifier_items[-1] if verifier_items else {}
    latest_plan = replan_items[-1] if replan_items else planner
    decision = latest_verifier.get("decision")
    if decision == "goal":
        status = "completed"
    elif decision == "terminal":
        status = "terminated"
    else:
        status = "in_progress"

    revisions = [
        item.get("revision")
        for item in [*planner_items, *executor_items, *verifier_items, *replan_items]
        if isinstance(item.get("revision"), int)
    ]
    completed = {
        str(item["step_id"])
        for item in executor_items
        if item.get("status") == "success" and item.get("step_id")
    }
    failed = {
        str(item["step_id"])
        for item in executor_items
        if item.get("status") == "failed" and item.get("step_id")
    }
    latest_executor = executor_items[-1] if executor_items else {}
    termination_code = None
    if status == "terminated":
        termination_code = latest_verifier.get("error_code") or latest_executor.get("error_code")

    return {
        "status": status,
        "plan_id": planner.get("plan_id"),
        "revision": max(revisions) if revisions else planner.get("revision"),
        "source": latest_plan.get("source"),
        "step_count": latest_plan.get("step_count", 0),
        "completed_step_count": len(completed),
        "failed_step_count": len(failed),
        "execution_count": len(executor_items),
        "replan_count": max(
            (int(item.get("replan_count", 0)) for item in replan_items),
            default=0,
        ),
        "current_step_id": latest_executor.get("step_id"),
        "final_decision": decision,
        "termination_code": termination_code,
    }


def _model_usage_summary(trace_items: list[dict]) -> dict:
    summaries = [item.get("model_usage") for item in trace_items if isinstance(item.get("model_usage"), dict)]
    if not summaries:
        return {"status": "not_available"}
    latest = summaries[-1]
    fields = (
        "call_count",
        "status_counts",
        "model_counts",
        "usage_source_counts",
        "total_latency_ms",
        "known_input_tokens",
        "known_output_tokens",
        "known_total_tokens",
        "tokens_complete",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "known_total_cost_usd",
        "cost_complete",
        "total_cost_usd",
        "cost_scope",
    )
    return {field: latest.get(field) for field in fields}


def _memory_summary(request: Request, flags: dict) -> dict:
    row = request.app.state.db_conn.execute("SELECT COUNT(*) AS count FROM memory_event").fetchone()
    return {
        "write_enabled": flags["memory_write_enabled"],
        "read_enabled": flags["memory_read_enabled"],
        "event_count": int(row["count"] if row is not None else 0),
    }
