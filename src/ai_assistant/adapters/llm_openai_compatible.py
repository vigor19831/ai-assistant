"""OpenAI-compatible LLM (works with any OpenAI-compatible API)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import httpx

from ai_assistant.core.domain.configs import LLMConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.closable import IClosable
from ai_assistant.core.ports.llm import ILLM, Message
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["OpenAICompatibleLLM"]

_logger = get_logger("llm.openai_compatible")


class OpenAICompatibleLLM(ILLM, IClosable):
    """LLM using OpenAI-compatible REST API."""

    def __init__(self, config: LLMConfigData) -> None:
        super().__init__(config)
        self.model: str = config.model
        self.api_base: str = config.api_base
        self.api_key: str = resolve_api_key(config.api_key, "OPENAI_API_KEY")
        self.max_tokens: int = config.max_tokens
        self.temperature: float = config.temperature
        self._timeout: float = config.timeout
        self._max_stream_tokens: int = config.max_tokens * 2
        self._client: httpx.AsyncClient | None = None

    async def shutdown(self) -> None:
        """Close persistent HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role = getattr(m, "role", None)
            if role == "user":
                content = getattr(m, "text", "") or ""
                image = getattr(m, "image", None)
                if image is not None:
                    parts: list[dict[str, Any]] = [{"type": "text", "text": content}]
                    image_url = getattr(image, "url", None)
                    if image_url:
                        parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            }
                        )
                    else:
                        base64_data = getattr(image, "base64_data", None)
                        if base64_data:
                            mime_type = getattr(image, "mime_type", "image/png")
                            data_url = f"data:{mime_type};base64,{base64_data}"
                            parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": data_url},
                                }
                            )
                    out.append({"role": "user", "content": parts})
                else:
                    out.append({"role": "user", "content": content})
            elif role == "assistant":
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": getattr(m, "text", "") or "",
                }
                tool_calls = getattr(m, "tool_calls", None)
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                out.append(msg)
            elif role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "content": getattr(m, "content", ""),
                        "tool_call_id": getattr(m, "tool_call_id", ""),
                    }
                )
            else:
                _logger.warning("Unknown message type in _build_messages: %s", type(m))
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
                _logger.warning("Skipping non-dict tool_call: %s", tc)
                continue
            if ttype == "function":
                if not tid or not name:
                    _logger.warning("Skipping incomplete function tool_call: %s", tc)
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
                _logger.warning("Unknown tool_call type %r; skipping: %s", ttype, tc)
        return parsed

    def get_context_limit(self) -> int | None:
        """Return context limit from config."""
        cfg = self.config
        limit = cfg.server_context_size
        if limit is not None and limit > 0:
            return limit
        limit = cfg.max_tokens
        if limit > 0:
            return limit
        return None

    @with_retry(max_retries=3, delay=1.0, jitter=True, max_delay=30.0)
    async def _complete_impl(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        max_tok = max_tokens if max_tokens is not None else self.max_tokens
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": max_tok,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        resp = await self._client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        try:
            choice = data["choices"][0]
            msg = choice.get("message", {})
        except (IndexError, KeyError, TypeError) as exc:
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
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        max_tok = max_tokens if max_tokens is not None else self.max_tokens
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": max_tok,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": True,
        }
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        async with self._client.stream(
            "POST", url, headers=headers, json=payload
        ) as resp:
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
                    # tool_calls in delta are ignored — see docstring
                except (KeyError, IndexError, TypeError) as exc:
                    _logger.warning("Malformed SSE: %s (%s)", obj, exc)
                    continue

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
