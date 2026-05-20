"""Simple fixed-size chunker."""

from __future__ import annotations

import uuid
from typing import Any

from core.domain.documents import Chunk, ChunkMetadata, Document
from core.ports.chunker import IChunker
from core.registry import register


@register("chunker", "simple")
class SimpleChunker(IChunker):
    """Split text into fixed-size chunks with overlap."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.chunk_size: int = config.chunk_size
        self.chunk_overlap: int = config.chunk_overlap

    async def chunk(self, document: Document) -> list[Chunk]:
        text = document.content
        if not text:
            return []

        size = self.chunk_size
        overlap = self.chunk_overlap
        step = max(1, size - overlap)

        chunks: list[Chunk] = []
        total = max(1, (len(text) + step - 1) // step)
        idx = 0
        for i in range(0, len(text), step):
            chunk_text = text[i : i + size]
            if not chunk_text.strip():
                continue
            meta = ChunkMetadata(
                source=document.id,
                index=idx,
                total_chunks=total,
                custom=document.metadata,
            )
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    text=chunk_text,
                    metadata=meta,
                )
            )
            idx += 1

        # Update total_chunks accurately
        for c in chunks:
            if c.metadata:
                object.__setattr__(c.metadata, "total_chunks", len(chunks))
        return chunks
