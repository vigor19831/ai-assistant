"""Local reranker adapter — HTTP client for Cohere-compatible /rerank endpoint.

Compatible with:
- llama.cpp --rerank (returns raw logits, normalized via sigmoid)
- Ollama (with reranker model)
- Any local server exposing POST /rerank in Cohere format

Note: llama.cpp reranker returns raw logits (-inf, +inf) rather than
probabilities (0..1). We apply sigmoid normalization so that the
threshold config works consistently across providers.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import httpx

from ai_assistant.adapters._http import async_post_json
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.reranker import IReranker, RerankResult
from ai_assistant.core.retry import with_retry

if TYPE_CHECKING:
    from ai_assistant.core.domain.configs import RerankerConfigData
    from ai_assistant.core.domain.documents import Chunk

_logger = get_logger("adapters.reranker_local")


def _normalize_score(raw: float) -> float:
    """Convert raw logit to probability-like score via sigmoid.

    llama.cpp --rerank returns unbounded logits. Sigmoid maps them
    to (0, 1) so that config.threshold works consistently.
    """
    # Clamp to prevent overflow in exp()
    if raw > 10.0:
        return 0.9999
    if raw < -10.0:
        return 0.0001
    return 1.0 / (1.0 + math.exp(-raw))


@register("reranker", "local")
class LocalReranker(IReranker):
    """HTTP client for local reranker server."""

    def __init__(self, config: RerankerConfigData) -> None:
        self.config = config
        self._client = httpx.AsyncClient(timeout=config.timeout)

    async def shutdown(self) -> None:
        """Close HTTP client unconditionally."""
        await self._client.aclose()

    @with_retry(max_retries=3, delay=1.0, backoff=2.0)
    async def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Rerank chunks by relevance to query via local /rerank endpoint.

        Args:
            query: Original user query.
            chunks: Chunks from vector store retrieval.
            top_k: Max results to return. None = return all scored.

        Returns:
            List of RerankResult sorted by score descending,
            filtered by config.threshold. Scores are normalized
            to (0, 1) via sigmoid for llama.cpp compatibility.
        """
        if not chunks:
            return []

        documents = [chunk.text for chunk in chunks]
        payload: dict[str, object] = {
            "query": query,
            "documents": documents,
            "top_n": top_k if top_k is not None else len(chunks),
            "model": self.config.model,
        }

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        url = f"{self.config.api_base.rstrip('/')}/rerank"

        try:
            data = await async_post_json(
                self._client,
                url,
                headers,
                payload,
            )
        except Exception as exc:
            _logger.exception("Local reranker request failed")
            raise AdapterError(f"Local reranker request failed: {exc}") from exc

        try:
            results = data["results"]
            if not isinstance(results, list):
                raise AdapterError(
                    f"Expected 'results' list, got {type(results).__name__}"
                )
        except KeyError:
            _logger.exception("Missing 'results' in reranker response")
            raise AdapterError("Missing 'results' in reranker response") from None

        scored: list[RerankResult] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            raw_score = item.get("relevance_score")
            if (
                not isinstance(idx, int)
                or idx < 0
                or idx >= len(chunks)
                or not isinstance(raw_score, (int, float))
            ):
                continue
            normalized = _normalize_score(float(raw_score))
            if normalized >= self.config.threshold:
                scored.append(RerankResult(chunk=chunks[idx], score=normalized))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored
