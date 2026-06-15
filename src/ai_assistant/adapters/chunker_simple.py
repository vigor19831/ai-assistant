"""Simple fixed-size chunker."""

from __future__ import annotations

import uuid

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import ChunkerConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.ports.chunker import IChunker

__all__ = ["SimpleChunker"]


@register("chunker", "simple")
class SimpleChunker(IChunker):
    """Split text into fixed-size chunks with overlap."""

    def __init__(self, config: ChunkerConfigData) -> None:
        super().__init__(config)
        self.chunk_size: int = config.chunk_size
        self.chunk_overlap: int = config.chunk_overlap
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be > 0, got {self.chunk_size}")
        if self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be >= 0, got {self.chunk_overlap}")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be < "
                f"chunk_size ({self.chunk_size})"
            )

    async def chunk(self, document: Document) -> list[Chunk]:
        text = document.content
        if not text:
            return []

        size = self.chunk_size
        overlap = self.chunk_overlap
        step = size - overlap

        chunk_texts: list[str] = []
        for i in range(0, len(text), step):
            chunk_text = text[i : i + size]
            if chunk_text.strip():
                chunk_texts.append(chunk_text)

        total = len(chunk_texts)
        return [
            Chunk(
                id=str(uuid.uuid4()),
                text=ct,
                metadata=ChunkMetadata(
                    source=document.id,
                    index=idx,
                    total_chunks=total,
                    custom=document.metadata.copy(),
                ),
            )
            for idx, ct in enumerate(chunk_texts)
        ]

    async def shutdown(self) -> None:
        """No-op shutdown — no external resources."""
        pass
