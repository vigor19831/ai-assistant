"""Pipeline data carrier."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .documents import Chunk
    from .messages import AssistantMessage, UserMessage

__all__ = ["PipelineData"]


@dataclass(frozen=True)
class PipelineData:
    query: UserMessage | None = None
    chunks: tuple[Chunk, ...] = field(default_factory=tuple)
    context: str = ""
    response: AssistantMessage | None = None
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    errors: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Глубокая неизменяемость: принудительно замораживаем вложенные контейнеры.
        # object.__setattr__ обходит frozen dataclass, позволяя перезаписать поле
        # после того, как сгенерированный __init__ уже отработал.
        if not isinstance(self.chunks, tuple):
            object.__setattr__(self, "chunks", tuple(self.chunks))
        if not isinstance(self.errors, tuple):
            object.__setattr__(self, "errors", tuple(self.errors))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

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
