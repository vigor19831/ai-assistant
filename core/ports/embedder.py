"""Embedder port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IEmbedder(ABC):
    """Text embedding interface."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed list of texts."""
        ...
