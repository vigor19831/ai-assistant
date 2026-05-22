"""OpenAI-compatible LLM (works with any OpenAI-compatible API)."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.domain.messages import AssistantMessage, UserMessage
from core.ports.llm import ILLM
from core.registry import register
from core.retry import with_retry
from core.utils import resolve_api_key

logger = logging.getLogger(__name__)


@register("llm", "openai_compatible")
class OpenAICompatibleLLM(ILLM):
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
        self._timeout: float = config.timeout
        self._max_stream_tokens: int = getattr(
            config, "max_stream_tokens", self.max_tokens * 2
        )

    def _build_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, dict):
                out.append(m)
            elif isinstance(m, UserMessage):
                content = m.text or ""
                if m.image:
                    content_parts: list[dict[str, Any]] = [
                        {"type": "text", "text": content}
                    ]
                    if m.image.url:
                        content_parts.append(
                            {"type": "image_url", "image_url": {"url": m.image.url}}
                        )
                    elif m.image.base64_data:
                        data_url = (
                            f"data:{m.image.mime_type};base64,{m.image.base64_data}"
                        )
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            }
                        )
                    out.append({"role": "user", "content": content_parts})
                else:
                    out.append({"role": "user", "content": content})
            elif isinstance(m, AssistantMessage):
                msg: dict[str, Any] = {"role": "assistant", "content": m.text or ""}
                if m.tool_calls:
                    msg["tool_calls"] = m.tool_calls
                out.append(msg)
        return out

    @with_retry(max_retries=3, delay=1.0)
    async def complete(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
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
        choice = data["choices"][0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        text = msg.get("content", "") or ""
        # Client-side cutoff
        if len(text.split()) > max_tok * 2:
            logger.warning(
                "Response exceeded safety limit (%d tokens), truncating",
                max_tok * 2,
            )
            text = " ".join(text.split()[: max_tok * 2]) + "…"
        return AssistantMessage(text=text, tool_calls=tool_calls)

    async def stream(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
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
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as resp:
                resp.raise_for_status()
                buffer = ""
                token_count = 0
                async for line in resp.aiter_lines():
                    # Skip SSE comments and empty lines
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        # Reset buffer if this standalone chunk is not JSON-like
                        if (
                            not buffer
                            and chunk.strip()
                            and chunk.strip()[0] not in "{["
                        ):
                            continue
                        buffer += chunk
                        try:
                            obj = json.loads(buffer)
                        except json.JSONDecodeError:
                            continue
                        buffer = ""
                        try:
                            choices = obj.get("choices", [])
                            if not choices:
                                continue
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                token_count += 1
                                if token_count > self._max_stream_tokens:
                                    logger.warning(
                                        "Stream exceeded max_stream_tokens (%d), "
                                        "aborting",
                                        self._max_stream_tokens,
                                    )
                                    return
                                yield content
                            # Yield tool_calls delta if present
                            tool_calls_delta = delta.get("tool_calls")
                            if tool_calls_delta:
                                for tc in tool_calls_delta:
                                    if tc.get("function", {}).get("arguments"):
                                        token_count += 1
                                        if token_count > self._max_stream_tokens:
                                            logger.warning(
                                                "Stream exceeded "
                                                "max_stream_tokens (%d), aborting",
                                                self._max_stream_tokens,
                                            )
                                            return
                                        yield tc["function"]["arguments"]
                        except (KeyError, IndexError, TypeError) as e:
                            logger.warning("Malformed SSE chunk: %s (%s)", obj, e)
                            continue
                    else:
                        logger.debug("Unexpected SSE line: %s", line)
                # Drain remaining buffer
                if buffer:
                    logger.warning("Unprocessed SSE buffer at stream end: %s", buffer)
