from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, *, context: list[str] | None = None) -> str:
        """Generate text for a prompt."""

