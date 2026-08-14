from __future__ import annotations

import uuid

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import ChunkerConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.ports.chunker import IChunker


@register("chunker", "recursive")
class RecursiveChunker(IChunker):
    """Split documents recursively by a hierarchy of separators.

    Tries to keep paragraphs intact, then lines, then sentences,
    then words. Falls back to character-level split only when a
    piece exceeds the configured chunk size.
    """

    _SEPARATORS: tuple[str, ...] = (
        "\n\n",
        "\n",
        ". ",
        "? ",
        "! ",
        " ",
        "",
    )

    def __init__(self, config: ChunkerConfigData) -> None:
        super().__init__(config)
        if config.chunk_size <= 0:
            raise ValueError(f"chunk_size must be > 0, got {config.chunk_size}")
        if config.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be >= 0, got {config.chunk_overlap}")
        if config.chunk_overlap >= config.chunk_size:
            raise ValueError(
                f"chunk_overlap ({config.chunk_overlap}) must be < "
                f"chunk_size ({config.chunk_size})"
            )
        self._chunk_size = config.chunk_size
        # Reserve room for overlap so final chunk never exceeds chunk_size.
        self._split_target = max(1, config.chunk_size - config.chunk_overlap)

    async def chunk(self, document: Document) -> list[Chunk]:
        """Return chunks for *document* using recursive splitting."""
        texts = self._split_text(document.content, self._SEPARATORS)
        texts = self._apply_overlap(texts)
        total = len(texts)
        custom_meta = document.metadata.copy()
        custom_meta.pop("source_uri", None)

        return [
            Chunk(
                id=str(uuid.uuid4()),
                text=text,
                metadata=ChunkMetadata(
                    source=document.id,
                    index=idx,
                    total_chunks=total,
                    custom=custom_meta,
                    original_path=document.metadata.get("original_path"),
                    source_uri=document.metadata.get("source_uri"),
                ),
            )
            for idx, text in enumerate(texts)
        ]

    def _split_text(self, text: str, separators: tuple[str, ...]) -> list[str]:
        """Recursively split *text* into chunks <= chunk_size."""
        if not text:
            return []

        chunk_size = self._split_target
        sep = separators[0]
        next_seps = separators[1:] if len(separators) > 1 else ("",)

        if sep:
            parts = text.split(sep)
            pieces = [parts[i] + sep for i in range(len(parts) - 1)]
            if parts[-1]:
                pieces.append(parts[-1])
        else:
            pieces = list(text)

        chunks: list[str] = []
        current = ""

        for piece in pieces:
            if not piece:
                continue

            if len(piece) > chunk_size:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_text(piece, next_seps))
                continue

            if current and len(current) + len(piece) > chunk_size:
                chunks.append(current)
                current = piece
            else:
                current += piece

        if current:
            chunks.append(current)

        return [c.rstrip() for c in chunks if c.strip()]

    def _apply_overlap(self, chunks: list[str]) -> list[str]:
        """Apply sentence-aware overlap between adjacent chunks.

        Prefers taking a complete sentence from the previous chunk.
        Falls back to the last *chunk_overlap* characters if the
        sentence does not fit.
        """
        overlap = self.config.chunk_overlap
        if not chunks or overlap <= 0:
            return chunks

        result = [chunks[0]]
        sentence_seps = (". ", "? ", "! ")

        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            overlap_text = ""

            best_pos = -1
            for sep in sentence_seps:
                pos = prev.rfind(sep)
                if pos > best_pos:
                    best_pos = pos

            if best_pos != -1:
                candidate = prev[best_pos:]
                if len(candidate) <= overlap:
                    overlap_text = candidate
                else:
                    overlap_text = prev[-overlap:]
            else:
                overlap_text = prev[-overlap:]

            result.append(overlap_text + chunks[i])

        return result

    async def shutdown(self) -> None:
        """No-op — stateless adapter."""
        pass
