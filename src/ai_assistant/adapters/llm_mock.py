"""Mock LLM — works without API keys or local models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.ports.llm import ILLM, Message
from ai_assistant.core.registry import register

__all__ = ["MockLLM"]


@register("llm", "mock")
class MockLLM(ILLM):
    """Deterministic echo LLM for testing."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        if not messages:
            last = "..."
        else:
            msg = messages[-1]
            if isinstance(msg, (UserMessage, AssistantMessage)):
                last = msg.text if msg.text is not None else "..."
            elif isinstance(msg, dict):
                last = msg.get("text") or "..."
            else:
                last = "..."
        return AssistantMessage(text=f"[MOCK LLM] Echo: {last}")

    async def stream(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        yield (
            "[MOCK] Server is running. Switch config.yaml to "
            "'llamacpp' or 'openai_compatible' for real responses."
        )
