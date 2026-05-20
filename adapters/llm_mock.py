"""Mock LLM — works without API keys or local models."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from core.domain.messages import AssistantMessage, UserMessage
from core.ports.llm import ILLM
from core.registry import register


@register("llm", "mock")
class MockLLM(ILLM):
    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def complete(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AssistantMessage:
        last = messages[-1].text if messages else "..."
        return AssistantMessage(text=f"[MOCK LLM] Echo: {last}")

    async def stream(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
        yield (
            "[MOCK] Server is running. Switch config.yaml to 'llamacpp' "
            "or 'openai_compatible' for real responses."
        )
