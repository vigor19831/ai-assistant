"""LLM port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.messages import AssistantMessage, UserMessage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

Message = UserMessage | AssistantMessage | dict[str, Any]

__all__ = ["ILLM", "Message"]


class ILLM(ABC):
    """Language model interface."""

    system_message: str | None = None

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        """Non-streaming completion."""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]: ...
