from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.schemas.agent import AgentState
from backend.app.schemas.api import ChatRequest
from backend.app.schemas.measurement import BodyMeasurementValues, MeasurementInput
from backend.app.schemas.rag_server import RagSearchHit, RagSearchResult


def test_agent_state_defaults_are_empty_collections() -> None:
    state = AgentState(session_id="s1", user_query="犊牛腹泻怎么办")

    assert state.retrieved_contexts == []
    assert state.tool_results == {}
    assert state.errors == []
    assert state.need_follow_up is False


def test_rag_result_schema_supports_hits_and_citations() -> None:
    result = RagSearchResult(
        query="q",
        hits=[
            RagSearchHit(
                chunk_id="c1",
                document_title="doc",
                content="content",
                score=0.8,
            )
        ],
    )

    assert result.has_usable_hits is True


def test_chat_request_requires_query() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(query="")


def test_measurement_input_requires_at_least_one_value() -> None:
    with pytest.raises(ValidationError):
        BodyMeasurementValues()

    measurement = MeasurementInput(
        animal_id="yak_001",
        current={"body_height_cm": 112.4},
        confidence=0.82,
    )

    assert measurement.current.body_height_cm == 112.4

