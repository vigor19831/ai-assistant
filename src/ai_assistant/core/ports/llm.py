"""LLM port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.messages import AssistantMessage, ToolMessage, UserMessage
from ai_assistant.core.ports.closable import IClosable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

Message = UserMessage | AssistantMessage | ToolMessage

__all__ = ["ILLM", "Message"]


class ILLM(IClosable, ABC):
    """Language model interface."""

    system_message: str | None = None

    def __init__(self, config: Any) -> None:
        self.config = config

    async def shutdown(self) -> None:
        """Default no-op shutdown for LLMs without external resources."""
        pass

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

    @abstractmethod
    def get_context_limit(self) -> int | None:
        """Return the context window size in tokens, or None if unknown."""
        ...
