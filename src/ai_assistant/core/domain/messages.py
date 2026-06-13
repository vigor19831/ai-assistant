from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class UserMessage:
    """User message."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    """Assistant message."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ToolMessage:
    """Tool result message."""

    text: str
    call_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
