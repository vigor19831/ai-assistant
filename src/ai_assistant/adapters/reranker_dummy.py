"""Dummy reranker — transparent pass-through, no-op fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk
from ai_assistant.core.ports.reranker import IReranker, RerankResult
from ai_assistant.core.registry import register

__all__ = ["DummyReranker"]


@register("reranker", "dummy")
class DummyReranker(IReranker):
    """Transparent reranker — returns chunks as-is with uniform scores.

    Used when no real reranker is configured. Maintains backward compatibility.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def rerank(
        self, query: str, chunks: list[Chunk], top_k: int | None = None
    ) -> list[RerankResult]:
        """Return chunks with score=1.0, preserving original order."""
        results = [RerankResult(chunk=c, score=1.0) for c in chunks]
        if top_k is not None:
            results = results[:top_k]
        return results
