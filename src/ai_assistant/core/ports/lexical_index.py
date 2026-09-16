"""Lexical index port -- exact-term retrieval over stored chunks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ai_assistant.core.ports.closable import IClosable

if TYPE_CHECKING:
    from ai_assistant.core.domain.configs import LexicalIndexConfigData
    from ai_assistant.core.domain.documents import Chunk

__all__ = ["ILexicalIndex"]


class ILexicalIndex(IClosable, ABC):
    """Exact-term (lexical) index over chunk texts, per namespace.

    The lexical twin of IVectorStore: same lifecycle (add / upsert /
    delete / save / load / list_namespaces), but search takes raw
    query text instead of an embedding. The vector store remains the
    single inventory authority: callers decide chunk ids and enforce
    capacity there, then pass the same lists here, so the two indexes
    cannot diverge in content -- only in timing.
    """

    def __init__(self, config: LexicalIndexConfigData) -> None:
        self.config = config

    @property
    @abstractmethod
    def index_path(self) -> str:
        """Return the base directory for index persistence."""
        ...

    @abstractmethod
    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Add chunks to a namespace (in-memory; persist via save()).

        Re-adding an existing chunk id replaces that chunk
        (idempotent). No capacity check: the vector store owns
        max_chunks (drift #48/#107).
        """
        ...

    @abstractmethod
    async def upsert(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Replace chunks for each source document.

        Same contract and ordering as IVectorStore.upsert (drift #88):
        add new chunks first, then delete old chunks of the same
        sources; an empty list is a no-op.
        """
        ...

    @abstractmethod
    async def search(
        self,
        query_text: str,
        top_k: int = 5,
        namespace: str = "default",
    ) -> list[Chunk]:
        """Search by raw text in a namespace.

        Returns chunks ordered by relevance score desc, ties broken
        by chunk id asc (deterministic). No matches (unknown
        namespace, unknown terms, empty query) -> empty list.
        """
        ...

    @abstractmethod
    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        """Delete chunks by ID and persist the change.

        Same contract as IVectorStore.delete: save to disk as part of
        the operation, roll back in-memory state if persistence
        fails, and remove the namespace files when it becomes empty
        so deleted chunks cannot reappear after restart (drift #40).
        """
        ...

    @abstractmethod
    async def save(self, path: str, namespace: str = "default") -> None:
        """Persist namespace index. Never-loaded namespaces write
        nothing (drift #41)."""
        ...

    @abstractmethod
    async def load(self, path: str, namespace: str = "default") -> None:
        """Load a namespace index. A missing file means an empty
        index (not an error); an unsupported format version raises
        VersionMismatchError (rebuild by reindexing -- sources are
        canonical, indices are derived data)."""
        ...

    @abstractmethod
    async def list_namespaces(self, path: str) -> list[str]:
        """Return sorted namespace names available under path."""
        ...
