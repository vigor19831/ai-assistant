"""Tests for malformed SSE (Server-Sent Events) handling.

Validates robustness against:
- Invalid JSON in SSE chunks
- Missing [DONE] terminator
- Empty/null content chunks
- Partial/malformed delta objects
- JSON injection in handler error payloads
"""

from __future__ import annotations

import json

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
from ai_assistant.api.deps import get_state
from ai_assistant.core.config import LLMConfig
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.main import create_app

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


# ── Handler-level SSE error JSON injection ──


async def _malicious_stream(*args, **kwargs):
    """Raise on first iteration — must be async generator for async for."""
    raise ValueError('Error with "quotes" and \n newlines')
    yield ""  # noqa: B901 — unreachable, but forces async generator protocol


def test_chat_stream_json_injection(mock_state, monkeypatch):
    """SSE error payload must be valid JSON even if exception contains quotes/newlines."""
    mock_state.chat_manager.stream_chat = _malicious_stream

    app = create_app(state=mock_state, lifespan=None)
    app.dependency_overrides[get_state] = lambda: mock_state

    monkeypatch.setattr(
        "ai_assistant.api.security.get_expected_api_key", lambda: "test-key"
    )

    client = TestClient(
        app,
        base_url="http://localhost",
        headers={"Authorization": "Bearer test-key"},
        raise_server_exceptions=True,
    )

    resp = client.post(
        "/api/v1/chat/stream",
        json={"message": 'test "quoted" and newline'},
    )
    assert resp.status_code == 200

    lines = [line for line in resp.text.splitlines() if line.startswith("data:")]
    assert len(lines) >= 1
    for line in lines:
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        data = json.loads(payload)
        assert data.get("error") == "Internal server error"


def test_openai_chat_stream_json_injection(mock_state, monkeypatch):
    """OpenAI-compatible SSE error payload must be valid JSON."""
    mock_state.chat_manager.stream_chat = _malicious_stream

    app = create_app(state=mock_state, lifespan=None)
    app.dependency_overrides[get_state] = lambda: mock_state

    monkeypatch.setattr(
        "ai_assistant.api.security.get_expected_api_key", lambda: "test-key"
    )

    client = TestClient(
        app,
        base_url="http://localhost",
        headers={"Authorization": "Bearer test-key"},
        raise_server_exceptions=True,
    )

    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "test",
            "messages": [{"role": "user", "content": 'test "quoted" and newline'}],
            "stream": True,
        },
    )
    assert resp.status_code == 200

    lines = [line for line in resp.text.splitlines() if line.startswith("data:")]
    assert len(lines) >= 1
    for line in lines:
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        data = json.loads(payload)
        assert "error" in data
        assert data["error"] == "Internal server error"
