"""Mock LLM — works without API keys or local models."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import LLMConfigData
from ai_assistant.core.domain.messages import AssistantMessage
from ai_assistant.core.ports.llm import ILLM, Message

__all__ = ["MockLLM"]


@register("llm", "mock")
class MockLLM(ILLM):
    """Deterministic echo LLM for testing."""

    def __init__(self, config: LLMConfigData) -> None:
        super().__init__(config)

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | str | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
    ) -> AssistantMessage:
        if not messages:
            last = "..."
        else:
            msg = messages[-1]
            # All message types have .text; ToolMessage has .text too
            last = getattr(msg, "text", None) or getattr(msg, "content", None) or "..."
        return AssistantMessage(text=f"[MOCK LLM] Echo: {last}")

    def stream(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | str | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
    ) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            yield (
                "[MOCK] Server is running. Switch config.yaml to "
                "'llamacpp' or 'openai_compatible' for real responses."
            )
        return _gen()
    def get_context_limit(self) -> int | None:
        """Return context limit from config, or default 4096."""
        cfg = self.config
        limit = cfg.server_context_size
        if limit is not None and limit > 0:
            return limit
        limit = cfg.max_tokens
        if limit > 0:
            return limit
        return 4096
