"""Message domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "AssistantMessage",
    "MessageRole",
    "TextPayload",
    "UserMessage",
]


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class TextPayload:
    content: str


@dataclass(frozen=True)
class UserMessage:
    role: MessageRole = field(default=MessageRole.USER, init=False)
    text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.text is None:
            raise ValueError("UserMessage must contain text payload")


@dataclass(frozen=True)
class AssistantMessage:
    role: MessageRole = field(default=MessageRole.ASSISTANT, init=False)
    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
