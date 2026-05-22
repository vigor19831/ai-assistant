"""Message domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "AssistantMessage",
    "ImagePayload",
    "MessageRole",
    "TextPayload",
    "UserMessage",
    "VoicePayload",
]


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class TextPayload:
    content: str


@dataclass(frozen=True)
class ImagePayload:
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "image/png"


@dataclass(frozen=True)
class VoicePayload:
    audio_base64: str
    mime_type: str = "audio/wav"
    duration_ms: int | None = None


@dataclass(frozen=True)
class UserMessage:
    role: MessageRole = field(default=MessageRole.USER, init=False)
    text: str | None = None
    image: ImagePayload | None = None
    voice: VoicePayload | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.text is None and self.image is None and self.voice is None:
            raise ValueError("UserMessage must contain at least one payload")


@dataclass(frozen=True)
class AssistantMessage:
    role: MessageRole = field(default=MessageRole.ASSISTANT, init=False)
    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
