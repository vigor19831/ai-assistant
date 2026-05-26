"""OpenAI-compatible LLM (works with any OpenAI-compatible API)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import httpx

from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.closable import IClosable
from ai_assistant.core.ports.llm import ILLM, Message
from ai_assistant.core.registry import register
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["OpenAICompatibleLLM"]

_logger = get_logger("llm.openai_compatible")


@register("llm", "openai_compatible")
class OpenAICompatibleLLM(ILLM, IClosable):
    """LLM using OpenAI-compatible REST API."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.model: str = getattr(config, "model", "gpt-4o-mini")
        self.api_base: str = getattr(config, "api_base", "https://api.openai.com/v1")
        self.api_key: str = resolve_api_key(
            getattr(config, "api_key", None), "OPENAI_API_KEY"
        )
        self.max_tokens: int = getattr(config, "max_tokens", 4096)
        self.temperature: float = getattr(config, "temperature", 0.7)
        self._timeout: float = getattr(config, "timeout", 300.0)
        self._max_stream_tokens: int = getattr(
            config, "max_stream_tokens", self.max_tokens * 2
        )

    async def shutdown(self) -> None:
        """No-op: client is created per-request and auto-closed by context manager."""
        pass

    def _build_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, dict):
                out.append(m)
            elif isinstance(m, UserMessage):
                content = m.text or ""
                if m.image:
                    parts: list[dict[str, Any]] = [{"type": "text", "text": content}]
                    if m.image.url:
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": m.image.url},
                            }
                        )
                    elif m.image.base64_data:
                        data_url = (
                            f"data:{m.image.mime_type};base64,{m.image.base64_data}"
                        )
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            }
                        )
                    out.append({"role": "user", "content": parts})
                else:
                    out.append({"role": "user", "content": content})
            elif isinstance(m, AssistantMessage):
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": m.text or "",
                }
                if m.tool_calls:
                    msg["tool_calls"] = m.tool_calls
                out.append(msg)
        return out

    @with_retry(max_retries=3, delay=1.0, jitter=True, max_delay=30.0)
    async def complete(
        self,
        messages: list[Message],
        **kwargs: Any,
    ) -> AssistantMessage:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        max_tok = kwargs.get("max_tokens", self.max_tokens)
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": max_tok,
            "temperature": kwargs.get("temperature", self.temperature),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
        except (IndexError, KeyError, TypeError) as exc:
            raise AdapterError(f"Unexpected response shape: {exc}") from exc

        tool_calls = msg.get("tool_calls", [])
        text = msg.get("content", "") or ""
        return AssistantMessage(text=text, tool_calls=tool_calls)

    async def stream(
        self,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream tokens. No automatic retry on network errors."""
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        max_tok = kwargs.get("max_tokens", self.max_tokens)
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": max_tok,
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": True,
        }
        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream("POST", url, headers=headers, json=payload) as resp,
        ):
            resp.raise_for_status()
            token_count = 0
            async for line in resp.aiter_lines():
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data: "):
                    _logger.debug("Unexpected SSE line: %s", line)
                    continue
                chunk = line[6:]
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                try:
                    choices = obj.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        token_count += 1
                        if token_count > self._max_stream_tokens:
                            _logger.warning(
                                "Stream limit (%d) reached",
                                self._max_stream_tokens,
                            )
                            return
                        yield content
                    tcd = delta.get("tool_calls")
                    if tcd:
                        for tc in tcd:
                            args = tc.get("function", {}).get("arguments")
                            if args:
                                token_count += 1
                                if token_count > self._max_stream_tokens:
                                    _logger.warning(
                                        "Stream limit (%d) reached",
                                        self._max_stream_tokens,
                                    )
                                    return
                                yield args
                except (KeyError, IndexError, TypeError) as exc:
                    _logger.warning("Malformed SSE: %s (%s)", obj, exc)
                    continue
