"""OpenAI-compatible LLM (works with any OpenAI-compatible API)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import httpx

from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage, MessageRole
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.closable import IClosable
from ai_assistant.core.ports.llm import ILLM, Message
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["OpenAICompatibleLLM"]

_logger = get_logger("llm.openai_compatible")


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
        self._client: httpx.AsyncClient | None = None

    async def shutdown(self) -> None:
        """Close persistent HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            role_attr = getattr(m, "role", None)
            if role_attr is None:
                out.append(m)
                continue
            if role_attr == MessageRole.USER:
                content = m.text or ""
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
            else:
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": m.text or "",
                }
                tool_calls = getattr(m, "tool_calls", None)
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                out.append(msg)
        return out

    @staticmethod
    def _parse_tool_calls(raw: Any) -> list[dict[str, Any]]:
        """Validate and normalize tool_calls from OpenAI API response."""
        if not isinstance(raw, list):
            return []
        parsed: list[dict[str, Any]] = []
        for tc in raw:
            if not isinstance(tc, dict):
                _logger.warning("Skipping non-dict tool_call: %s", tc)
                continue
            tid = tc.get("id")
            ttype = tc.get("type")
            func = tc.get("function", {})
            if not isinstance(func, dict):
                _logger.warning("Skipping tool_call without function dict: %s", tc)
                continue
            name = func.get("name")
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
        """Actual streaming implementation."""
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
        async with self._client.stream("POST", url, headers=headers, json=payload) as resp:
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
                        _logger.warning(
                            "Tool calls in streaming mode are not supported by current "
                            "ILLM contract; received %d delta(s). Ignoring.",
                            len(tcd),
                        )
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
