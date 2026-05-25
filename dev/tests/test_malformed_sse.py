"""Tests for malformed SSE (Server-Sent Events) handling.

Validates robustness against:
- Invalid JSON in SSE chunks
- Missing [DONE] terminator
- Empty/null content chunks
- Partial/malformed delta objects
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
from ai_assistant.core.config import LLMConfig
from ai_assistant.core.domain.messages import UserMessage

# ── OpenAICompatibleLLM malformed SSE ──


class TestOpenAICompatibleMalformedSSE:
    @pytest.fixture
    def llm(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_base="https://api.test.com/v1",
            api_key="test-key",
            max_tokens=50,
            temperature=0.7,
            timeout=5.0,
            stop_sequences=[],
        )
        return OpenAICompatibleLLM(config)

    @pytest.mark.asyncio
    async def test_invalid_json_skipped(self, llm):
        """Invalid JSON should be silently skipped (not yielded)."""
        sse = (
            "data: not json\n\n"
            'data: {"choices":[{"delta":{"content":"valid"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        with respx.mock:
            respx.post(
                "https://api.test.com/v1/chat/completions"
            ).return_value = Response(
                200, text=sse, headers={"content-type": "text/event-stream"}
            )
            chunks = [c async for c in llm.stream([UserMessage(text="hi")])]
            assert chunks == ["valid"]

    @pytest.mark.asyncio
    async def test_empty_delta_content_skipped(self, llm):
        """Empty content in delta should be skipped."""
        sse = (
            'data: {"choices":[{"delta":{"content":""}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"real"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        with respx.mock:
            respx.post(
                "https://api.test.com/v1/chat/completions"
            ).return_value = Response(
                200, text=sse, headers={"content-type": "text/event-stream"}
            )
            chunks = [c async for c in llm.stream([UserMessage(text="hi")])]
            assert chunks == ["real"]

    @pytest.mark.asyncio
    async def test_missing_done_runs_to_end(self, llm):
        """Without [DONE], stream yields all valid chunks."""
        sse = (
            'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"b"}}]}\n\n'
        )
        with respx.mock:
            respx.post(
                "https://api.test.com/v1/chat/completions"
            ).return_value = Response(
                200, text=sse, headers={"content-type": "text/event-stream"}
            )
            chunks = [c async for c in llm.stream([UserMessage(text="hi")])]
            assert "".join(chunks) == "ab"
