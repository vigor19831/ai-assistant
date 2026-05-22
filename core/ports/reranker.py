"""Reranker port — post-retrieval relevance scoring."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.domain.documents import Chunk

__all__ = ["IReranker", "RerankResult"]


@dataclass
class RerankResult:
    """Single rerank result with relevance score."""

    chunk: Chunk
    score: float  # 0.0 to 1.0, higher = more relevant


class IReranker(ABC):
    """Re-rank retrieved chunks by relevance to query.

    Used after vector store retrieval to filter out false positives
    and improve context quality for generation.
    """

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Rerank chunks by relevance to query.

        Args:
            query: Original user query.
            chunks: Chunks from vector store retrieval.
            top_k: Max results to return. None = return all scored.

        Returns:
            List of RerankResult sorted by score descending.
        """
        ...
