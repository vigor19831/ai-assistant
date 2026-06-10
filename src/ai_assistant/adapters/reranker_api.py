"""Cross-encoder reranker via OpenAI-compatible /rerank API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.ports.reranker import IReranker, RerankResult
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key

__all__ = ["APIReranker"]


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

    async def shutdown(self) -> None:
        """No-op shutdown — client is created per-call."""
        pass

    @with_retry(max_retries=2, delay=1.0, jitter=True, max_delay=15.0)
    async def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Rerank chunks via API and filter by relevance threshold."""
        if not chunks:
            return []

        url = f"{self.api_base}/v1/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        docs = [c.text for c in chunks]
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

        try:
            raw_results = data["results"]
        except (KeyError, TypeError) as exc:
            raise AdapterError(f"Unexpected rerank response shape: {exc}") from exc

        results: list[RerankResult] = []
        for item in raw_results:
            try:
                idx = int(item["index"])
                score = float(item["relevance_score"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= idx < len(chunks) and score >= self._threshold:
                results.append(RerankResult(chunk=chunks[idx], score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        if top_k is not None:
            results = results[:top_k]

        return results
