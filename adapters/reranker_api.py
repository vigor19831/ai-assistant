"""Cross-encoder reranker via OpenAI-compatible /rerank API."""

from __future__ import annotations

from typing import Any

import httpx

from core.domain.documents import Chunk
from core.ports.reranker import IReranker, RerankResult
from core.registry import register
from core.retry import with_retry
from core.utils import resolve_api_key


@register("reranker", "api")
class APIReranker(IReranker):
    """Cross-encoder reranker using external API (OpenAI-compatible /rerank).

    Compatible with:
    - Cohere /rerank
    - Jina AI /rerank
    - Any OpenAI-compatible rerank endpoint
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.api_base: str = getattr(config, "api_base", "https://api.cohere.com")
        self.api_key: str = resolve_api_key(
            getattr(config, "api_key", None), "RERANK_API_KEY"
        )
        self.model: str = getattr(config, "model", "rerank-multilingual-v3.0")
        self._timeout: float = getattr(config, "timeout", 30.0)
        self._threshold: float = getattr(config, "threshold", 0.3)

    @with_retry(max_retries=2, delay=1.0)
    async def rerank(
        self, query: str, chunks: list[Chunk], top_k: int | None = None
    ) -> list[RerankResult]:
        """Rerank chunks via API and filter by relevance threshold."""
        if not chunks:
            return []

        url = f"{self.api_base}/v1/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        docs = [c.text for c in chunks if c.text]
        if not docs:
            return []
        payload = {
            "model": self.model,
            "query": query,
            "documents": docs,
            "top_n": top_k or len(chunks),
            "return_documents": False,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Map API results back to chunks
        results: list[RerankResult] = []
        for item in data.get("results", []):
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            if idx < len(chunks) and score >= self._threshold:
                results.append(RerankResult(chunk=chunks[idx], score=score))

        # Sort by score descending (API usually returns sorted, but ensure)
        results.sort(key=lambda r: r.score, reverse=True)

        if top_k is not None:
            results = results[:top_k]

        return results
