from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from backend.app.agent.langgraph_workflow import (
    build_chat_graph,
    build_measurement_graph,
    validate_tool_plan,
)


def _edge_pairs(graph: CompiledStateGraph) -> set[tuple[str, str]]:
    drawable = graph.get_graph()
    return {(edge.source, edge.target) for edge in drawable.edges}


def test_chat_graph_is_a_real_compiled_state_graph_with_required_nodes_and_edges() -> None:
    graph = build_chat_graph()

    assert isinstance(graph, CompiledStateGraph)
    drawable = graph.get_graph()
    assert {
            "context",
            "memory_search",
        "router",
        "direct",
        "disease_prepare",
        "planner",
        "tool",
        "reasoning",
        "verifier",
        "safety",
            "final",
            "memory_write",
    }.issubset(drawable.nodes)
    assert {
        ("__start__", "context"),
            ("context", "memory_search"),
            ("memory_search", "router"),
        ("router", "direct"),
        ("router", "disease_prepare"),
        ("router", "planner"),
        ("disease_prepare", "planner"),
        ("planner", "tool"),
        ("tool", "tool"),
        ("tool", "reasoning"),
        ("reasoning", "verifier"),
        ("verifier", "safety"),
        ("safety", "final"),
            ("final", "memory_write"),
            ("memory_write", "__end__"),
    }.issubset(_edge_pairs(graph))


def test_measurement_graph_is_a_real_compiled_state_graph_without_tool_path() -> None:
    graph = build_measurement_graph()

    assert isinstance(graph, CompiledStateGraph)
    drawable = graph.get_graph()
    assert {
            "context",
            "memory_search",
        "router",
        "measurement",
        "verifier",
        "safety",
            "final",
            "memory_write",
    }.issubset(drawable.nodes)
    assert "tool" not in drawable.nodes
    assert {
        ("__start__", "context"),
            ("context", "memory_search"),
            ("memory_search", "router"),
        ("router", "measurement"),
        ("measurement", "verifier"),
        ("verifier", "safety"),
        ("safety", "final"),
            ("final", "memory_write"),
            ("memory_write", "__end__"),
    }.issubset(_edge_pairs(graph))


def test_tool_plan_validation_allows_only_one_knowledge_hub_query() -> None:
    allowed, error_code = validate_tool_plan(
        [
            {
                "tool": "query_knowledge_hub",
                "arguments": {"query": "cattle heat-stress feeding", "top_k": 4},
            }
        ]
    )

    assert allowed is True
    assert error_code is None


def test_tool_plan_validation_rejects_missing_unknown_and_multi_tool_plans() -> None:
    assert validate_tool_plan([]) == (False, "PLAN_MISSING")
    assert validate_tool_plan(
        [{"tool": "shell_command", "arguments": {"command": "whoami"}}]
    ) == (False, "PLANNER_TOOL_NOT_ALLOWED")
    assert validate_tool_plan(
        [
            {"tool": "query_knowledge_hub", "arguments": {"query": "cattle feeding"}},
            {"tool": "query_knowledge_hub", "arguments": {"query": "second query"}},
        ]
    ) == (False, "PLANNER_TOOL_NOT_ALLOWED")


def test_tool_plan_validation_rejects_invalid_knowledge_hub_arguments() -> None:
    invalid_arguments = [
        {},
        {"query": "   "},
        {"query": "cattle feeding", "top_k": 0},
        {"query": "cattle feeding", "top_k": 21},
        {"query": "cattle feeding", "top_k": True},
        {"query": "cattle feeding", "top_k": "4"},
    ]

    for arguments in invalid_arguments:
        assert validate_tool_plan(
            [{"tool": "query_knowledge_hub", "arguments": arguments}]
        ) == (False, "PLANNER_TOOL_ARGUMENTS_INVALID")
