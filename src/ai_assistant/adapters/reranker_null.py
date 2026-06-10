"""Null reranker — no-op pass-through for optional reranker support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk

from ai_assistant.core.ports.reranker import IReranker, RerankResult

__all__ = ["NullReranker"]


class NullReranker(IReranker):
    """No-op reranker that returns chunks unchanged."""

    def __init__(self, config: Any = None) -> None:
        # config may be None when created implicitly
        super().__init__(config or object())

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
