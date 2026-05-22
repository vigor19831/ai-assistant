"""OpenAI-compatible embedder (works with any OpenAI-compatible API)."""

from __future__ import annotations

from typing import Any

import httpx

from core.domain.errors import AdapterError
from core.ports.embedder import IEmbedder
from core.registry import register
from core.retry import with_retry
from core.utils import resolve_api_key


@register("embedder", "openai_compatible")
class OpenAICompatibleEmbedder(IEmbedder):
    """Embedder using OpenAI-compatible REST API."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.model: str = getattr(config, "model", "text-embedding-3-small")
        self.api_base: str = getattr(config, "api_base", "https://api.openai.com/v1")
        self.api_key: str = resolve_api_key(
            getattr(config, "api_key", None), "OPENAI_API_KEY"
        )
        self._dim: int = getattr(config, "dim", 1536)
        self._timeout: float = config.timeout

    @property
    def dimension(self) -> int:
        return self._dim

    @with_retry(max_retries=3, delay=1.0)
    async def embed(self, texts: list[str]) -> list[list[float]]:
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
        embeddings = [item["embedding"] for item in data["data"]]

        # Validate dimension consistency
        for i, emb in enumerate(embeddings):
            if len(emb) != self._dim:
                raise AdapterError(
                    f"Dimension mismatch: expected {self._dim}, "
                    f"got {len(emb)} for text[{i}] "
                    f"(model={self.model!r}). "
                    f"Check config.embedder.dim or model compatibility."
                )
        return embeddings
