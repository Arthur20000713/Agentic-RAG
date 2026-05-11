from __future__ import annotations

from backend.app.model.base import BaseLLMClient


class TemplateLLM(BaseLLMClient):
    async def generate(self, prompt: str, *, context: list[str] | None = None) -> str:
        context = context or []
        if context:
            joined_context = "\n".join(f"- {item}" for item in context)
            return f"问题：{prompt}\n依据：\n{joined_context}\n回答：请结合以上依据进行保守说明。"
        return f"问题：{prompt}\n回答：当前没有额外依据，请保持保守。"

