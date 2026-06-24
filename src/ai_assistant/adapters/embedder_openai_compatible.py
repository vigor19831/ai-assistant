"""OpenAI-compatible embedder (works with any OpenAI-compatible API)."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import EmbedderConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["OpenAICompatibleEmbedder"]

_logger = get_logger("embedder_openai_compatible")


def _extract_embeddings(
    resp_text: str, expected_dim: int, model: str
) -> list[list[float]]:
    data = json.loads(resp_text)
    try:
        embeddings = [item["embedding"] for item in data["data"]]
    except (KeyError, TypeError) as exc:
        _logger.exception(
            "Unexpected embedder response shape",
            extra={"model": model},
        )
        raise AdapterError(f"Unexpected response shape from {model!r}: {exc}") from exc

    for i, emb in enumerate(embeddings):
        if len(emb) != expected_dim:
            raise AdapterError(
                f"Dimension mismatch: expected {expected_dim}, "
                f"got {len(emb)} for text[{i}] "
                f"(model={model!r}). "
                f"Check config.embedder.dim or model compatibility."
            )
    return embeddings


@register("embedder", "openai_compatible")
class OpenAICompatibleEmbedder(IEmbedder):
    """Embedder using OpenAI-compatible REST API."""

    def __init__(self, config: EmbedderConfigData) -> None:
        super().__init__(config)
        self.model: str = config.model
        self.api_base: str = config.api_base
        if config.api_key is not None:
            self.api_key: str = resolve_api_key(config.api_key, "OPENAI_API_KEY")
        else:
            self.api_key = os.getenv("AI_EMBEDDER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        self._dim: int = config.dim
        self._timeout: float = config.timeout
        self._connect_timeout: float | None = config.connect_timeout
        timeout = (
            httpx.Timeout(self._timeout, connect=self._connect_timeout)
            if self._connect_timeout is not None
            else self._timeout
        )
        self._client: httpx.AsyncClient = httpx.AsyncClient(timeout=timeout)
        self._closed: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

    async def shutdown(self) -> None:
        """Close persistent HTTP client."""
        async with self._lock:
            if self._closed:
                return
            self._closed = True
        await self._client.aclose()

    def _check_open(self) -> None:
        """Raise AdapterError if adapter has been shut down."""
        if self._closed:
            raise AdapterError("Embedder adapter is shutting down")

    @property
    def dimension(self) -> int:
        return self._dim

    @with_retry(max_retries=3, delay=1.0, jitter=True, max_delay=30.0)
    async def _post_embeddings(self, payload: dict[str, Any]) -> str:
        """Execute HTTP POST to embeddings endpoint (retryable)."""
        self._check_open()
        url = f"{self.api_base}/embeddings"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = await self._client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings from remote API.

        Raises:
            AdapterError: On dimension mismatch or HTTP failure.
        """
        if not texts:
            return []
        payload = {
            "model": self.model,
            "input": texts,
        }
        try:
            resp_text = await self._post_embeddings(payload)
        except httpx.HTTPError as exc:
            _logger.exception(
                "Embedder HTTP request failed",
                extra={"error": str(exc)},
            )
            raise AdapterError(f"Embedder HTTP request failed: {exc}") from exc
        embeddings = await asyncio.to_thread(
            _extract_embeddings, resp_text, self._dim, self.model
        )
        return embeddings
