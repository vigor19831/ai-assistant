"""Pipeline data carrier."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .documents import Chunk
    from .messages import AssistantMessage, UserMessage

__all__ = ["PipelineData"]


@dataclass(frozen=True)
class PipelineData:
    query: UserMessage | None = None
    chunks: list[Chunk] = field(default_factory=list)
    context: str = ""
    response: AssistantMessage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def with_chunks(self, chunks: list[Chunk]) -> PipelineData:
        """Return a new PipelineData with updated chunks."""
        return replace(self, chunks=chunks)

    def with_context(self, context: str) -> PipelineData:
        """Return a new PipelineData with updated context."""
        return replace(self, context=context)

    def with_response(self, response: AssistantMessage | None) -> PipelineData:
        """Return a new PipelineData with updated response."""
        return replace(self, response=response)

    def add_error(self, msg: str) -> PipelineData:
        """Return a new PipelineData with an additional error message."""
        return replace(self, errors=[*self.errors, msg])
