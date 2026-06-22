from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Immutable metadata for a chunk."""

    source: str
    index: int
    total_chunks: int
    custom: dict[str, Any] = field(default_factory=dict)
    original_path: str | None = None
    source_uri: str | None = None  # Relative path from root (documents_root / chat_exports_root), e.g. "personal/notes.md"


@dataclass(frozen=True, slots=True)
class Chunk:
    """Immutable text chunk with optional embedding and metadata."""

    id: str
    text: str
    embedding: list[float] | None = None
    metadata: ChunkMetadata | None = None


@dataclass(frozen=True, slots=True)
class Document:
    """Immutable source document."""

    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
