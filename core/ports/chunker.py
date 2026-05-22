"""Chunker port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.domain.documents import Chunk, Document

__all__ = ["IChunker"]


class IChunker(ABC):
    """Split documents into chunks."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def chunk(self, document: Document) -> list[Chunk]:
        """Split document into chunks."""
        ...
