from __future__ import annotations

import asyncio

from backend.app.core.config import load_settings
from backend.app.integrations.rag_server import create_rag_server_client
from backend.app.integrations.rag_server.base import RagServerClient


def test_factory_returns_contract_implementation_for_fake_mode() -> None:
    settings = load_settings("config/settings.test.yaml")
    client = create_rag_server_client(settings)

    assert isinstance(client, RagServerClient)


def test_fake_client_contract_methods_return_standard_shapes() -> None:
    settings = load_settings("config/settings.test.yaml")
    client = create_rag_server_client(settings)

    result = asyncio.run(client.query("犊牛腹泻怎么办"))
    summary = asyncio.run(client.get_document_summary("doc_001"))
    collections = asyncio.run(client.list_collections())

    assert result.query == "犊牛腹泻怎么办"
    assert result.hits
    assert summary.doc_id == "doc_001"
    assert "test" in collections

