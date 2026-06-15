"""OpenAI-compatible embedder (works with any OpenAI-compatible API)."""

from __future__ import annotations

import asyncio
import json
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
        self.api_key: str = resolve_api_key(config.api_key, "OPENAI_API_KEY")
        self._dim: int = config.dim
        self._timeout: float = config.timeout
        self._client: httpx.AsyncClient | None = None

    async def shutdown(self) -> None:
        """Close persistent HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def dimension(self) -> int:
        return self._dim

    @with_retry(max_retries=3, delay=1.0, jitter=True, max_delay=30.0)
    async def _post_embeddings(self, payload: dict[str, Any]) -> str:
        """Execute HTTP POST to embeddings endpoint (retryable)."""
        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        resp = await self._client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings from remote API.

        Raises:
            AdapterError: On dimension mismatch.
            httpx.HTTPStatusError: On non-2xx response (after retries).
        """
        if not texts:
            return []
        payload = {
            "model": self.model,
            "input": texts,
        }
        resp_text = await self._post_embeddings(payload)
        embeddings = await asyncio.to_thread(
            _extract_embeddings, resp_text, self._dim, self.model
        )
        return embeddings
