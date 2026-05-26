"""OpenAI-compatible embedder (works with any OpenAI-compatible API)."""

from __future__ import annotations

from typing import Any

import httpx

from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.ports.closable import IClosable
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.registry import register
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["OpenAICompatibleEmbedder"]


@register("embedder", "openai_compatible")
class OpenAICompatibleEmbedder(IEmbedder, IClosable):
    """Embedder using OpenAI-compatible REST API."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.model: str = getattr(config, "model", "text-embedding-3-small")
        self.api_base: str = getattr(config, "api_base", "https://api.openai.com/v1")
        self.api_key: str = resolve_api_key(
            getattr(config, "api_key", None), "OPENAI_API_KEY"
        )
        self._dim: int = getattr(config, "dim", 1536)
        self._timeout: float = getattr(config, "timeout", 60.0)

    async def shutdown(self) -> None:
        """No-op: client is created per-request and auto-closed by context manager."""
        pass

    @property
    def dimension(self) -> int:
        return self._dim

    @with_retry(max_retries=3, delay=1.0, jitter=True, max_delay=30.0)
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings from remote API.

        Raises:
            AdapterError: On dimension mismatch.
            httpx.HTTPStatusError: On non-2xx response (after retries).
        """
        if not texts:
            return []
        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        try:
            embeddings = [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError) as exc:
            raise AdapterError(
                f"Unexpected response shape from {self.model!r}: {exc}"
            ) from exc

        for i, emb in enumerate(embeddings):
            if len(emb) != self._dim:
                raise AdapterError(
                    f"Dimension mismatch: expected {self._dim}, "
                    f"got {len(emb)} for text[{i}] "
                    f"(model={self.model!r}). "
                    f"Check config.embedder.dim or model compatibility."
                )
        return embeddings
