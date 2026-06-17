"""Pipeline data carrier."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .documents import Chunk
    from .messages import AssistantMessage, UserMessage

__all__ = ["PipelineData", "PipelineConfig"]


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Typed configuration for RAG pipeline steps.

    Mirrors a subset of RAGConfig as a stdlib dataclass
    so that pipeline steps have a typed contract without
    depending on Pydantic.
    """

    top_k: int = 5
    namespace: str = "default"
    relevance_threshold: float = 0.3
    prompt_name: str = "rag_strict"
    prompt_version: str = "v1"
    token_margin_min: int = 256
    token_margin_pct: float = 0.1


@dataclass(frozen=True, slots=True)
class PipelineData:
    query: UserMessage | None = None
    chunks: tuple[Chunk, ...] = field(default_factory=tuple)
    context: str = ""
    response: AssistantMessage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = field(default_factory=tuple)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def with_chunks(self, chunks: list[Chunk] | tuple[Chunk, ...]) -> PipelineData:
        """Return a new PipelineData with updated chunks."""
        return replace(self, chunks=tuple(chunks))

    def with_context(self, context: str) -> PipelineData:
        """Return a new PipelineData with updated context."""
        return replace(self, context=context)

    def with_response(self, response: AssistantMessage | None) -> PipelineData:
        """Return a new PipelineData with updated response."""
        return replace(self, response=response)

    def add_error(self, msg: str) -> PipelineData:
        """Return a new PipelineData with an additional error message."""
        return replace(self, errors=(*self.errors, msg))
