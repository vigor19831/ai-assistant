"""OpenAI-compatible embedder (works with any OpenAI-compatible API)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from ai_assistant.adapters._http import async_post_json
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import EmbedderConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["OpenAICompatibleEmbedder"]

_logger = get_logger("embedder_openai_compatible")

_DEFAULT_BATCH_SIZE: int = 100


def _extract_embeddings(
    data: dict[str, Any], expected_dim: int, model: str, expected_count: int
) -> list[list[float]]:
    try:
        embeddings = [item["embedding"] for item in data["data"]]
    except (KeyError, TypeError) as exc:
        _logger.exception(
            "Unexpected embedder response shape",
            extra={"model": model},
        )
        raise AdapterError(f"Unexpected response shape from {model!r}: {exc}") from exc

    if len(embeddings) != expected_count:
        _logger.error(
            "Embedding count mismatch",
            extra={
                "expected_count": expected_count,
                "got_count": len(embeddings),
                "model": model,
            },
        )
        raise AdapterError(
            f"Embedding count mismatch: expected {expected_count}, "
            f"got {len(embeddings)} (model={model!r})"
        )

    for i, emb in enumerate(embeddings):
        if len(emb) != expected_dim:
            _logger.error(
                "Dimension mismatch",
                extra={
                    "expected": expected_dim,
                    "got": len(emb),
                    "index": i,
                },
            )
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

    async def shutdown(self) -> None:
        """Close HTTP client unconditionally."""
        await self._client.aclose()

    @property
    def dimension(self) -> int:
        return self._dim

    @with_retry(max_retries=3, delay=1.0, jitter=True, max_delay=30.0)
    async def _post_embeddings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute HTTP POST to embeddings endpoint (retryable)."""
        url = f"{self.api_base}/embeddings"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            return await async_post_json(self._client, url, headers, payload)
        except RuntimeError as exc:
            if "closed" in str(exc).lower():
                raise AdapterError("Embedder adapter is shutting down") from exc
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings from remote API with batching.

        Raises:
            AdapterError: On dimension mismatch, count mismatch, or HTTP failure.
        """
        if not texts:
            return []
        result: list[list[float]] = []
        for i in range(0, len(texts), _DEFAULT_BATCH_SIZE):
            batch = texts[i:i + _DEFAULT_BATCH_SIZE]
            payload = {
                "model": self.model,
                "input": batch,
            }
            data = await self._post_embeddings(payload)
            embeddings = await asyncio.to_thread(
                _extract_embeddings, data, self._dim, self.model, len(batch)
            )
            result.extend(embeddings)
        return result
