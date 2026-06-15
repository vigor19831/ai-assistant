"""Null reranker — no-op pass-through for optional reranker support."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import RerankerConfigData
from ai_assistant.core.ports.reranker import IReranker, RerankResult

__all__ = ["NullReranker"]


@register("reranker", "null")
class NullReranker(IReranker):
    """No-op reranker that returns chunks unchanged."""

    def __init__(self, config: RerankerConfigData | None = None) -> None:
        # config may be None when created implicitly in old tests
        super().__init__(config or RerankerConfigData())

    async def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Return all chunks with score 1.0, preserving original order."""
        return [RerankResult(chunk=c, score=1.0) for c in chunks]

    async def shutdown(self) -> None:
        """No-op shutdown — no external resources."""
        pass
