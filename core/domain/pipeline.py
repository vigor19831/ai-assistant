"""Pipeline data carrier."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .documents import Chunk
from .messages import AssistantMessage, UserMessage

__all__ = ["PipelineData"]


@dataclass
class PipelineData:
    query: UserMessage | None = None
    chunks: list[Chunk] = field(default_factory=list)
    context: str = ""
    response: AssistantMessage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def rebuild_context(self) -> None:
        """Rebuild context string from current chunks."""
        if not self.chunks:
            self.context = ""
            return
        lines = [chunk.text for chunk in self.chunks if chunk.text]
        self.context = "\n\n".join(lines)
