"""OpenAI-compatible LLM (works with any OpenAI-compatible API)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import httpx

from ai_assistant.adapters._http import async_post_json
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import LLMConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage, ToolMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.closable import IClosable
from ai_assistant.core.ports.llm import ILLM, Message
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["OpenAICompatibleLLM"]

_logger = get_logger("llm.openai_compatible")


@register("llm", "openai_compatible")
class OpenAICompatibleLLM(ILLM, IClosable):
    """LLM using OpenAI-compatible REST API."""

    def __init__(self, config: LLMConfigData) -> None:
        super().__init__(config)
        self.model: str = config.model
        self.api_base: str = config.api_base
        if config.api_key is not None:
            self.api_key: str = resolve_api_key(config.api_key, "OPENAI_API_KEY")
        else:
            self.api_key = os.getenv("AI_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self.max_tokens: int = config.max_tokens
        self.temperature: float = config.temperature
        self._timeout: float = config.timeout
        self._connect_timeout: float | None = config.connect_timeout
        self._max_stream_tokens: int = config.max_tokens * 2
        timeout = (
            httpx.Timeout(self._timeout, connect=self._connect_timeout)
            if self._connect_timeout is not None
            else self._timeout
        )
        self._client: httpx.AsyncClient = httpx.AsyncClient(timeout=timeout)
        self._closed: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

    async def shutdown(self) -> None:
        """Close HTTP client. Idempotent."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True
        await self._client.aclose()

    def _check_open(self) -> None:
        """Raise AdapterError if adapter has been shut down."""
        if self._closed:
            raise AdapterError("LLM adapter is shutting down")

    def _build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert domain Message objects to OpenAI API message dicts."""
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, UserMessage):
                out.append({"role": "user", "content": m.text or ""})
            elif isinstance(m, AssistantMessage):
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": m.text or "",
                }
                if m.tool_calls:
                    msg["tool_calls"] = m.tool_calls
                out.append(msg)
            elif isinstance(m, ToolMessage):
                out.append(
                    {
                        "role": "tool",
                        "content": m.text or "",
                        "tool_call_id": m.call_id,
                    }
                )
            else:
                _logger.warning(
                    "Unknown message type in _build_messages",
                    extra={"message_type": str(type(m))},
                )
                out.append({"role": "user", "content": str(m)})
        return out

    @staticmethod
    def _parse_tool_calls(raw: Any) -> list[dict[str, Any]]:
        """Validate and normalize tool_calls from OpenAI API response."""
        if raw is None:
            return []
        try:
            parsed_raw = list(raw)
        except TypeError:
            return []
        parsed: list[dict[str, Any]] = []
        for tc in parsed_raw:
            try:
                tid = tc.get("id")
                ttype = tc.get("type")
                func = tc.get("function", {})
                name = func.get("name")
            except AttributeError:
                _logger.warning(
                    "Skipping non-dict tool_call",
                    extra={"tool_call": str(tc)},
                )
                continue
            if ttype == "function":
                if not tid or not name:
                    _logger.warning(
                        "Skipping incomplete function tool_call",
                        extra={"tool_call": str(tc)},
                    )
                    continue
                parsed.append(
                    {
                        "id": tid,
                        "type": ttype,
                        "function": {
                            "name": name,
                            "arguments": func.get("arguments") or "",
                        },
                    }
                )
            else:
                _logger.warning(
                    "Unknown tool_call type; skipping",
                    extra={"tool_call_type": ttype, "tool_call": str(tc)},
                )
        return parsed

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

    @with_retry(max_retries=3, delay=1.0, jitter=True, max_delay=30.0)
    async def _complete_impl(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        self._check_open()
        url = f"{self.api_base}/chat/completions"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        max_tok = max_tokens if max_tokens is not None else self.max_tokens
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": max_tok,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        stop = [s for s in self.config.stop_sequences if s]
        if stop:
            payload["stop"] = stop
        data = await async_post_json(self._client, url, headers, payload)

        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
        except (IndexError, KeyError, TypeError) as exc:
            _logger.exception("Unexpected LLM response shape", extra={"response_preview": str(data)[:200]})
            raise AdapterError(f"Unexpected response shape: {exc}") from exc

        tool_calls = self._parse_tool_calls(msg.get("tool_calls"))
        text = msg.get("content", "") or ""
        return AssistantMessage(text=text, tool_calls=tool_calls)

    async def complete(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        """Non-streaming completion with retry."""
        return await self._complete_impl(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def _stream_impl(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Actual streaming implementation.

        Tool calls in streaming mode are ignored — IToolRegistry is not
        implemented (FUTURE.md: blocked). Only text content is yielded.
        """
        self._check_open()
        url = f"{self.api_base}/chat/completions"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        max_tok = max_tokens if max_tokens is not None else self.max_tokens
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": max_tok,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": True,
        }
        stop = [s for s in self.config.stop_sequences if s]
        if stop:
            payload["stop"] = stop
        try:
            async with self._client.stream(
                "POST", url, headers=headers, json=payload
            ) as resp:
                resp.raise_for_status()
                token_count = 0
                async for line in resp.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data: "):
                        _logger.debug(
                            "Unexpected SSE line",
                            extra={"line": line},
                        )
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
                        # tool_calls in delta are ignored — see docstring
                    except (KeyError, IndexError, TypeError) as exc:
                        _logger.warning(
                            "Malformed SSE",
                            extra={"obj": str(obj), "error": str(exc)},
                        )
                        continue
        except httpx.HTTPError as exc:
            _logger.exception(
                "LLM stream request failed",
                extra={"url": url, "error": str(exc)},
            )
            raise AdapterError(f"LLM stream request failed: {exc}") from exc

    async def stream(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens with retry."""
        async for chunk in self._stream_impl(
            messages, max_tokens=max_tokens, temperature=temperature
        ):
            yield chunk
