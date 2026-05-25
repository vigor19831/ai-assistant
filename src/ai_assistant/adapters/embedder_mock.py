"""Mock embedder — deterministic fake vectors, no network."""

from __future__ import annotations

import random
from typing import Any

from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.registry import register

__all__ = ["MockEmbedder"]


@register("embedder", "mock")
class MockEmbedder(IEmbedder):
    """Deterministic fake embedder for testing."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self._dim: int = config.dim

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for t in texts:
            rng = random.Random(abs(hash(t)))
            result.append([rng.random() for _ in range(self._dim)])
        return result
