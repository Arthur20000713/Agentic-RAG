from __future__ import annotations

import asyncio

from backend.app.model.template_client import TemplateLLM


def test_template_llm_is_deterministic() -> None:
    client = TemplateLLM()

    first = asyncio.run(client.generate("犊牛腹泻怎么办", context=["资料一", "资料二"]))
    second = asyncio.run(client.generate("犊牛腹泻怎么办", context=["资料一", "资料二"]))

    assert first == second
    assert "犊牛腹泻怎么办" in first
    assert "资料一" in first

