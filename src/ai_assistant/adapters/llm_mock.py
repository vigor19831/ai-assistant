"""Mock LLM — works without API keys or local models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from ai_assistant.core.domain.messages import AssistantMessage
from ai_assistant.core.ports.llm import ILLM, Message

__all__ = ["MockLLM"]


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
            # Duck typing: ToolMessage has .content, UserMessage/AssistantMessage have .text
            last = getattr(msg, "content", None) or getattr(msg, "text", None) or "..."
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

    def get_context_limit(self) -> int | None:
        """Return context limit from config, or default 4096."""
        cfg = self.config
        for attr in ("context_size", "server_context_size", "max_tokens"):
            limit = getattr(cfg, attr, None)
            if isinstance(limit, (int, float)) and limit > 0:
                return int(limit)
        return 4096
