"""OpenAI-compatible LLM (works with any OpenAI-compatible API)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.domain.messages import AssistantMessage, UserMessage
from core.ports.llm import ILLM
from core.registry import register
from core.retry import with_retry
from core.utils import resolve_api_key


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
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        return AssistantMessage(text=msg.get("content", ""), tool_calls=tool_calls)

    async def stream(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            obj = json.loads(chunk)
                            delta = obj["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
