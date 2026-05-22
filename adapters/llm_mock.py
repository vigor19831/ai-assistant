"""Mock LLM — works without API keys or local models."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from core.domain.messages import AssistantMessage
from core.ports.llm import ILLM, Message
from core.registry import register

__all__ = ["MockLLM"]


@register("llm", "mock")
class MockLLM(ILLM):
    """Deterministic echo LLM for testing."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def complete(
        self, messages: list[Message], **kwargs: Any
    ) -> AssistantMessage:
        if not messages:
            last = "..."
        else:
            msg = messages[-1]
            if isinstance(msg, dict):
                last = msg.get("text") or "..."
            else:
                last = msg.text if msg.text is not None else "..."
        return AssistantMessage(text=f"[MOCK LLM] Echo: {last}")

    async def stream(
        self, messages: list[Message], **kwargs: Any
    ) -> AsyncIterator[str]:
        yield (
            "[MOCK] Server is running. Switch config.yaml to "
            "'llamacpp' or 'openai_compatible' for real responses."
        )
