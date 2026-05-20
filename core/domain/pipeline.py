"""Pipeline data carrier."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .documents import Chunk
from .messages import AssistantMessage, UserMessage


@dataclass
class PipelineData:
    query: UserMessage | None = None
    chunks: list[Chunk] = field(default_factory=list)
    context: str = ""
    response: AssistantMessage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
