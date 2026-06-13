"""core/ports/embedder.py"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_assistant.core.domain.configs import EmbedderConfigData
from ai_assistant.core.ports.closable import IClosable

__all__ = ["IEmbedder"]


class IEmbedder(IClosable, ABC):
    """Text embedding interface."""

    def __init__(self, config: EmbedderConfigData) -> None:
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
