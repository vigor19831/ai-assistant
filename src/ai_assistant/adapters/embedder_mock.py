"""Mock embedder — deterministic fake vectors, no network."""

from __future__ import annotations

import random

from ai_assistant.core.domain.configs import EmbedderConfigData
from ai_assistant.core.ports.embedder import IEmbedder

__all__ = ["MockEmbedder"]


class MockEmbedder(IEmbedder):
    """Deterministic fake embedder for testing."""

    def __init__(self, config: EmbedderConfigData) -> None:
        super().__init__(config)
        self._dim: int = config.dim

    @property
    def dimension(self) -> int:
        return self._dim

    async def shutdown(self) -> None:
        pass

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for t in texts:
            rng = random.Random(abs(hash(t)))
            result.append([rng.random() for _ in range(self._dim)])
        return result
