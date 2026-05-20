"""Mock embedder — deterministic fake vectors, no network."""

from __future__ import annotations

import random
from typing import Any

from core.ports.embedder import IEmbedder
from core.registry import register


@register("embedder", "mock")
class MockEmbedder(IEmbedder):
    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self._dim: int = config.dim

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [random.Random(t + str(i)).random() for i in range(self._dim)]
            for t in texts
        ]
