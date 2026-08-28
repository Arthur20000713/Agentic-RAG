from __future__ import annotations

import asyncio

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from backend.app.agent.checkpointing import checkpoint_config
from backend.app.agent.langgraph_workflow import AgentGraphRuntime, build_chat_graph
from backend.app.agent.state import MultiAgentState
from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_chat_graph_accepts_checkpointer_and_store() -> None:
    checkpointer = InMemorySaver()
    store = InMemoryStore()
    graph = build_chat_graph(checkpointer=checkpointer, store=store)
    state = MultiAgentState(
        session_id="session_memory_graph",
        user_query="Tell me a joke.",
    )

    async def invoke():  # noqa: ANN202
        return await graph.ainvoke(
            state,
            config=checkpoint_config("user_memory_graph", state.session_id),
            context=AgentGraphRuntime(rag_client=FakeRagServerClient()),
        )

    result = MultiAgentState.model_validate(asyncio.run(invoke()))

    assert result.session_id == state.session_id
    assert checkpointer.get(checkpoint_config("user_memory_graph", state.session_id)) is not None
