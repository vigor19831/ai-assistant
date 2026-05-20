"""LLM port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from core.domain.messages import AssistantMessage, UserMessage


class ILLM(ABC):
    """Language model interface."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def complete(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AssistantMessage:
        """Non-streaming completion."""
        ...

    @abstractmethod
    def stream(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AsyncIterator[str]: ...
