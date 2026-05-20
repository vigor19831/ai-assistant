"""Document and chunk models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ChunkMetadata:
    source: str
    index: int
    total_chunks: int
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    id: str
    text: str
    embedding: list[float] | None = None
    metadata: ChunkMetadata | None = None


@dataclass
class Document:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)
