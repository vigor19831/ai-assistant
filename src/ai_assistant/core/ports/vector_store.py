"""Vector store port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk

__all__ = ["IVectorStore"]


class IVectorStore(ABC):
    """Vector storage with FAISS-like semantics."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Add chunks with embeddings to a namespace."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        namespace: str = "default",
    ) -> list[Chunk]:
        """Search by embedding in a namespace."""
        ...

    @abstractmethod
    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        """Delete chunks by ID from a namespace."""
        ...

    @abstractmethod
    async def save(self, path: str, namespace: str = "default") -> None:
        """Persist namespace index + metadata."""
        ...

    @abstractmethod
    async def load(self, path: str, namespace: str = "default") -> None:
        """Load namespace index + metadata. Validate version."""
        ...

    @abstractmethod
    async def list_by_filter(
        self,
        filters: dict[str, Any],
        namespace: str = "default",
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return (chunk_id, metadata) matching ALL filters key-values in namespace."""
        ...

    @abstractmethod
    async def list_namespaces(self, path: str) -> list[str]:
        """Return list of available namespace names."""
        ...
