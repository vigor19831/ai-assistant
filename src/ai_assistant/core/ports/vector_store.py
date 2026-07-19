"""core/ports/vector_store.py"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_assistant.core.domain.configs import VectorStoreConfigData
    from ai_assistant.core.domain.documents import Chunk

from ai_assistant.core.ports.closable import IClosable

__all__ = ["IVectorStore"]


class IVectorStore(IClosable, ABC):
    """Vector storage with FAISS-like semantics."""

    def __init__(self, config: VectorStoreConfigData) -> None:
        self.config = config

    @property
    @abstractmethod
    def index_path(self) -> str:
        """Return the base path for index persistence.

        Adapters must expose this so that lifespan and health checks
        can locate indices without reaching into config internals.
        """
        ...

    @abstractmethod
    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Add chunks with embeddings to a namespace."""
        ...

    async def upsert(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Replace chunks for each source document.

        For every unique ``ChunkMetadata.source`` in *chunks*, delete
        existing chunks with the same source in the namespace, then add
        the new ones.  If *chunks* is empty, this is a no-op.

        Adapters may override this for atomicity or performance.
        """
        if not chunks:
            return

        sources: set[str] = set()
        for chunk in chunks:
            if chunk.metadata is not None:
                sources.add(chunk.metadata.source)

        old_ids: list[str] = []
        for source in sources:
            old = await self.list_by_filter(
                {"source": source}, namespace=namespace
            )
            old_ids.extend(cid for cid, _ in old)

        if old_ids:
            await self.delete(old_ids, namespace=namespace)

        await self.add(chunks, namespace=namespace)

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
        """Delete chunks by ID from a namespace and persist the change.

        Implementations must save the index to disk as part of this
        operation. If persistence fails, the in-memory state must be
        rolled back to maintain consistency with disk.
        """
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
        filters: dict[str, str | int | float | bool | None],
        namespace: str = "default",
    ) -> list[tuple[str, dict[str, str | int | float | bool | None]]]:
        """Return (chunk_id, metadata) matching ALL filters key-values in namespace."""
        ...

    @abstractmethod
    async def list_namespaces(self, path: str) -> list[str]:
        """Return list of available namespace names."""
        ...
