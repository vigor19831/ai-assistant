"""core/ports/chunker.py"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_assistant.core.domain.configs import ChunkerConfigData
    from ai_assistant.core.domain.documents import Chunk, Document

from ai_assistant.core.ports.closable import IClosable

__all__ = ["IChunker"]


class IChunker(IClosable, ABC):
    """Split documents into chunks."""

    def __init__(self, config: ChunkerConfigData) -> None:
        self.config = config

    @abstractmethod
    async def chunk(self, document: Document) -> list[Chunk]:
        """Split document into chunks."""
        ...

    async def shutdown(self) -> None:
        """Default no-op shutdown — chunkers typically hold no external resources."""
        pass
