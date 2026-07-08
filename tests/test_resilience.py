"""respx-based integration tests for HTTP adapters.

These tests verify that OpenAI-compatible adapters handle network
failures, retries, malformed responses, and streaming correctly.
No unittest.mock — respx intercepts httpx at the transport layer.

Adding a new HTTP adapter? Add a new test class here — the pattern
is identical (respx.mock + route assertions).
"""

from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import Response

from ai_assistant.core.domain.configs import EmbedderConfigData, LLMConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder
from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM


# ---------------------------------------------------------------------------
# Embedder resilience
# ---------------------------------------------------------------------------

class TestEmbedderResilience:
    """respx tests for OpenAICompatibleEmbedder."""

    @pytest_asyncio.fixture
    async def embedder(self):
        """Fresh embedder with short timeout for fast tests."""
        e = OpenAICompatibleEmbedder(
            EmbedderConfigData(
                model="text-embedding-test",
                api_base="http://localhost:9999/v1",
                api_key="test-key",
                dim=384,
                timeout=1.0,
            )
        )
        yield e
        await e.shutdown()

    @pytest.mark.asyncio
    async def test_embed_success(self, embedder: OpenAICompatibleEmbedder) -> None:
        """Given: API returns valid embeddings.
        When: embed() is called.
        Then: returns embeddings with correct dimension.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            route = mock.post("http://localhost:9999/v1/embeddings").mock(
                return_value=Response(
                    200,
                    json={
                        "data": [
                            {"embedding": [0.1] * 384},
                            {"embedding": [0.2] * 384},
                        ]
                    },
                )
            )
            result = await embedder.embed(["hello", "world"])
            assert len(result) == 2
            assert len(result[0]) == 384
            assert route.called
            assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_embed_empty_input_returns_empty(
        self, embedder: OpenAICompatibleEmbedder
    ) -> None:
        """Given: empty texts list.
        When: embed([]) is called.
        Then: returns [] without HTTP call.
        """
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
            route = mock.post("http://localhost:9999/v1/embeddings")
            result = await embedder.embed([])
            assert result == []
            assert not route.called
            assert mock.calls.call_count == 0

    @pytest.mark.asyncio
    async def test_embed_500_then_success_with_retry(
        self, embedder: OpenAICompatibleEmbedder
    ) -> None:
        """Given: API returns 500 then 200.
        When: embed() is called (with_retry active).
        Then: succeeds after retry.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            route = mock.post("http://localhost:9999/v1/embeddings").mock(
                side_effect=[
                    Response(500, text="Internal Server Error"),
                    Response(
                        200,
                        json={"data": [{"embedding": [0.1] * 384}]},
                    ),
                ]
            )
            result = await embedder.embed(["hello"])
            assert len(result) == 1
            assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_dimension_mismatch_raises_adapter_error(
        self, embedder: OpenAICompatibleEmbedder
    ) -> None:
        """Given: API returns wrong dimension.
        When: embed() is called.
        Then: raises AdapterError with dimension info.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            mock.post("http://localhost:9999/v1/embeddings").mock(
                return_value=Response(
                    200,
                    json={"data": [{"embedding": [0.1] * 100}]},  # wrong dim
                )
            )
            with pytest.raises(AdapterError, match="Dimension mismatch"):
                await embedder.embed(["hello"])

    @pytest.mark.asyncio
    async def test_embed_malformed_response_raises_adapter_error(
        self, embedder: OpenAICompatibleEmbedder
    ) -> None:
        """Given: API returns malformed JSON (missing 'data').
        When: embed() is called.
        Then: raises AdapterError.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            mock.post("http://localhost:9999/v1/embeddings").mock(
                return_value=Response(200, json={"error": "bad"})
            )
            with pytest.raises(AdapterError, match="Unexpected response shape"):
                await embedder.embed(["hello"])

    @pytest.mark.asyncio
    async def test_embed_timeout_eventually_fails(
        self, embedder: OpenAICompatibleEmbedder
    ) -> None:
        """Given: API times out repeatedly.
        When: embed() is called.
        Then: raises AdapterError after exhausting retries.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            mock.post("http://localhost:9999/v1/embeddings").mock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )
            with pytest.raises(AdapterError, match="HTTP request failed"):
                await embedder.embed(["hello"])

    @pytest.mark.asyncio
    async def test_embed_shutdown_is_idempotent(self) -> None:
        """Given: fresh embedder.
        When: shutdown() is called multiple times.
        Then: no error on any call.
        """
        embedder = OpenAICompatibleEmbedder(
            EmbedderConfigData(
                model="text-embedding-test",
                api_base="http://localhost:9999/v1",
                api_key="test-key",
                dim=384,
                timeout=1.0,
            )
        )
        await embedder.shutdown()
        await embedder.shutdown()
        await embedder.shutdown()


# ---------------------------------------------------------------------------
# LLM resilience
# ---------------------------------------------------------------------------

class TestLLMResilience:
    """respx tests for OpenAICompatibleLLM."""

    @pytest_asyncio.fixture
    async def llm(self):
        """Fresh LLM with short timeout."""
        llm_instance = OpenAICompatibleLLM(
            LLMConfigData(
                model="gpt-test",
                api_base="http://localhost:9999/v1",
                api_key="test-key",
                max_tokens=100,
                temperature=0.7,
                timeout=1.0,
            )
        )
        yield llm_instance
        await llm_instance.shutdown()

    @pytest.mark.asyncio
    async def test_complete_success(self, llm: OpenAICompatibleLLM) -> None:
        """Given: API returns valid chat completion.
        When: complete() is called.
        Then: returns AssistantMessage with text.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            route = mock.post("http://localhost:9999/v1/chat/completions").mock(
                return_value=Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "Hello world",
                                }
                            }
                        ]
                    },
                )
            )
            result = await llm.complete([UserMessage(text="Hi")])
            assert result.text == "Hello world"
            assert route.called
            assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_complete_with_tool_calls(self, llm: OpenAICompatibleLLM) -> None:
        """Given: API returns tool calls.
        When: complete() is called.
        Then: AssistantMessage contains parsed tool_calls.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            mock.post("http://localhost:9999/v1/chat/completions").mock(
                return_value=Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "get_weather",
                                                "arguments": '{"city": "Berlin"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                )
            )
            result = await llm.complete([UserMessage(text="Weather?")])
            assert len(result.tool_calls) == 1
            assert result.tool_calls[0]["function"]["name"] == "get_weather"

    @pytest.mark.asyncio
    async def test_complete_malformed_response_raises(
        self, llm: OpenAICompatibleLLM
    ) -> None:
        """Given: API returns missing choices.
        When: complete() is called.
        Then: raises AdapterError.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            mock.post("http://localhost:9999/v1/chat/completions").mock(
                return_value=Response(200, json={"error": "bad"})
            )
            with pytest.raises(AdapterError, match="Unexpected response shape"):
                await llm.complete([UserMessage(text="Hi")])

    @pytest.mark.asyncio
    async def test_complete_500_then_retry(
        self, llm: OpenAICompatibleLLM
    ) -> None:
        """Given: API returns 500 then 200.
        When: complete() is called.
        Then: succeeds after retry.
        """
        with respx.mock(assert_all_mocked=True) as mock:
            route = mock.post("http://localhost:9999/v1/chat/completions").mock(
                side_effect=[
                    Response(500, text="Error"),
                    Response(
                        200,
                        json={
                            "choices": [
                                {"message": {"role": "assistant", "content": "OK"}}
                            ]
                        },
                    ),
                ]
            )
            result = await llm.complete([UserMessage(text="Hi")])
            assert result.text == "OK"
            assert route.call_count == 2

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self, llm: OpenAICompatibleLLM) -> None:
        """Given: API returns SSE stream.
        When: stream() is consumed.
        Then: yields text tokens.
        """
        sse_lines = "\n".join(
            [
                'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                'data: {"choices":[{"delta":{"content":" world"}}]}',
                "data: [DONE]",
            ]
        )

        with respx.mock(assert_all_mocked=True) as mock:
            route = mock.post("http://localhost:9999/v1/chat/completions").mock(
                return_value=Response(
                    200,
                    text=sse_lines,
                    headers={"content-type": "text/event-stream"},
                )
            )
            chunks = []
            async for chunk in llm.stream([UserMessage(text="Hi")]):
                chunks.append(chunk)

            assert chunks == ["Hello", " world"]
            assert route.called
            assert route.call_count == 1

    @pytest.mark.asyncio
    async def test_stream_ignores_malformed_sse(
        self, llm: OpenAICompatibleLLM
    ) -> None:
        """Given: API returns mixed valid/invalid SSE lines.
        When: stream() is consumed.
        Then: skips invalid lines, yields valid tokens.
        """
        sse_lines = "\n".join(
            [
                "data: not json",  # invalid
                'data: {"choices":[{"delta":{"content":"OK"}}]}',
                "data: [DONE]",
            ]
        )

        with respx.mock(assert_all_mocked=True) as mock:
            mock.post("http://localhost:9999/v1/chat/completions").mock(
                return_value=Response(
                    200,
                    text=sse_lines,
                    headers={"content-type": "text/event-stream"},
                )
            )
            chunks = []
            async for chunk in llm.stream([UserMessage(text="Hi")]):
                chunks.append(chunk)

            assert chunks == ["OK"]

    @pytest.mark.asyncio
    async def test_stream_respects_max_tokens_limit(
        self, llm: OpenAICompatibleLLM
    ) -> None:
        """Given: stream yields more tokens than max_tokens allows.
        When: stream() is consumed.
        Then: stops before yielding all tokens (bounded, not infinite).
        """
        # Generate many SSE lines — more than any reasonable max_tokens
        lines = [
            f'data: {json.dumps({"choices": [{"delta": {"content": "x"}}]})}'
            for _ in range(500)
        ]
        lines.append("data: [DONE]")
        sse_lines = "\n".join(lines)

        with respx.mock(assert_all_mocked=True) as mock:
            mock.post("http://localhost:9999/v1/chat/completions").mock(
                return_value=Response(
                    200,
                    text=sse_lines,
                    headers={"content-type": "text/event-stream"},
                )
            )
            chunks = []
            async for chunk in llm.stream([UserMessage(text="Hi")]):
                chunks.append(chunk)

            # Stream must be bounded — not all 500 tokens yielded
            assert len(chunks) < 500
            # And must have yielded something
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_llm_shutdown_is_idempotent(self) -> None:
        """Given: fresh LLM.
        When: shutdown() is called multiple times.
        Then: no error on any call.
        """
        llm = OpenAICompatibleLLM(
            LLMConfigData(
                model="gpt-test",
                api_base="http://localhost:9999/v1",
                api_key="test-key",
                max_tokens=100,
                temperature=0.7,
                timeout=1.0,
            )
        )
        await llm.shutdown()
        await llm.shutdown()
        await llm.shutdown()
