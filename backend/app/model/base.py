from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, *, context: list[str] | None = None) -> str:
        """Generate text for a prompt."""


class BaseModelClient(ABC):
    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate structured JSON for a low-risk model task."""
