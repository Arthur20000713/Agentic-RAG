from __future__ import annotations

import asyncio

from backend.app.integrations.rag_server.fake_client import FakeRagServerClient


def test_fake_client_returns_success_fixture() -> None:
    client = FakeRagServerClient()

    result = asyncio.run(client.query("犊牛腹泻怎么办", top_k=1))

    assert result.status == "success"
    assert len(result.hits) == 1
    assert result.citations[0].title == "犊牛腹泻防治技术手册"


def test_fake_client_returns_empty_fixture() -> None:
    client = FakeRagServerClient()

    result = asyncio.run(client.query("没有答案的问题"))

    assert result.status == "empty"
    assert result.hits == []


def test_fake_client_returns_error_fixture_without_fabricating_hits() -> None:
    client = FakeRagServerClient()

    result = asyncio.run(client.query("失败"))

    assert result.status == "error"
    assert result.hits == []
    assert result.error_code == "RAG_INTERNAL_ERROR"

