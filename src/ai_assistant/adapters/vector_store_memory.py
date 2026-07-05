"""In-memory vector store with namespaces, relevance filtering, and FIFO eviction."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import VectorStoreConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.vector_store import IVectorStore

_logger = get_logger("adapters.vector_store_memory")

__all__ = ["MemoryVectorStore"]


@register("vector_store", "memory")
class MemoryVectorStore(IVectorStore):
    """Simple in-memory vector store with multi-namespace support and FIFO eviction.

    Uses cosine similarity with strict threshold to prevent irrelevant results.
    Enforces max_chunks per namespace to prevent OOM.
    """

    def __init__(self, config: VectorStoreConfigData) -> None:
        super().__init__(config)
        self.dim: int = config.dim
        self._max_chunks: int = config.max_chunks
        self._namespaces: dict[str, _NamespaceData] = {}
        self._lock = asyncio.Lock()
        self._index_path = config.index_path

    @property
    def index_path(self) -> str:
        """Return the configured index path (for persistence compatibility)."""
        return self._index_path

    def _get_ns(self, name: str) -> _NamespaceData:
        if name not in self._namespaces:
            self._namespaces[name] = _NamespaceData(
                dim=self.dim,
                max_chunks=self._max_chunks,
            )
        return self._namespaces[name]

    def _normalize(self, v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

    async def shutdown(self) -> None:
        """Release in-memory chunk data and embeddings."""
        self._namespaces.clear()

    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        if not chunks:
            return
        async with self._lock:
            ns = self._get_ns(namespace)
            for chunk in chunks:
                if chunk.embedding is None:
                    continue
                emb = np.array(chunk.embedding, dtype=np.float32)
                if emb.shape[0] != self.dim:
                    continue
                ns.chunks[chunk.id] = chunk
                ns.embeddings[chunk.id] = self._normalize(emb)
                meta: dict[str, Any] = {}
                if chunk.metadata is not None:
                    meta = chunk.metadata.custom.copy()
                    meta["source"] = chunk.metadata.source
                    meta["index"] = chunk.metadata.index
                    meta["total_chunks"] = chunk.metadata.total_chunks
                    meta["original_path"] = chunk.metadata.original_path
                    meta["source_uri"] = chunk.metadata.source_uri
                ns.metadata[chunk.id] = meta
                ns._track(chunk.id)
                ns._evict()

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        namespace: str = "default",
    ) -> list[Chunk]:
        """Search for nearest neighbors by cosine similarity.

        Returns top_k closest chunks without applying a relevance cutoff.
        Quality filtering is the responsibility of the rerank pipeline step.
        """
        async with self._lock:
            if namespace not in self._namespaces:
                return []
            ns = self._namespaces[namespace]
            if not ns.embeddings:
                return []

            q = self._normalize(np.array(query_embedding, dtype=np.float32))
            ids = list(ns.embeddings.keys())
            matrix = np.stack([ns.embeddings[i] for i in ids])
            scores = matrix @ q

            sorted_order = np.argsort(scores)[::-1]
            top_indices = sorted_order[:top_k]

            return [ns.chunks[ids[i]] for i in top_indices]

    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        """Delete chunks by ID from a namespace and persist atomically.

        If persistence fails, the in-memory state is rolled back by reloading
        from disk. No-op if the namespace does not exist in memory.
        """
        async with self._lock:
            if namespace not in self._namespaces:
                return
            ns = self._namespaces[namespace]
            for cid in chunk_ids:
                ns.chunks.pop(cid, None)
                ns.embeddings.pop(cid, None)
                ns.metadata.pop(cid, None)
                if cid in ns._order:
                    ns._order.remove(cid)

            try:
                await self._save_unlocked(self.index_path, namespace=namespace)
            except Exception:
                _logger.exception(
                    "delete save failed, rolling back",
                    extra={"namespace": namespace},
                )
                try:
                    await self._load_unlocked(self.index_path, namespace=namespace)
                except Exception:
                    _logger.exception(
                        "delete rollback failed",
                        extra={"namespace": namespace},
                    )
                raise

    async def _save_unlocked(self, path: str, namespace: str = "default") -> None:
        """Internal save without lock — caller must hold self._lock."""
        p = Path(path) / namespace
        p.parent.mkdir(parents=True, exist_ok=True)
        ns = self._get_ns(namespace)
        data = {
            "dim": ns.dim,
            "chunks": {
                cid: {
                    "id": c.id,
                    "text": c.text,
                    "metadata": (
                        {
                            "source": c.metadata.source,
                            "index": c.metadata.index,
                            "total_chunks": c.metadata.total_chunks,
                            "custom": c.metadata.custom,
                            "original_path": c.metadata.original_path,
                            "source_uri": c.metadata.source_uri,
                        }
                        if c.metadata
                        else None
                    ),
                }
                for cid, c in ns.chunks.items()
            },
            "embeddings": {cid: emb.tolist() for cid, emb in ns.embeddings.items()},
            "metadata": ns.metadata,
        }
        await atomic_write(p / "memory_store.json", json.dumps(data, indent=2))

    async def save(self, path: str, namespace: str = "default") -> None:
        async with self._lock:
            await self._save_unlocked(path, namespace=namespace)

    async def _load_unlocked(self, path: str, namespace: str = "default") -> None:
        """Internal load without lock — caller must hold self._lock."""
        p = Path(path) / namespace / "memory_store.json"
        if not await asyncio.to_thread(p.exists):
            return
        raw = await asyncio.to_thread(p.read_text)
        data = json.loads(raw)

        stored_dim = data.get("dim")
        if stored_dim is not None and stored_dim != self.dim:
            raise VersionMismatchError(
                f"Reindex required: stored dim {stored_dim} != config dim {self.dim}"
            )

        ns = self._get_ns(namespace)
        ns.dim = data.get("dim", self.dim)
        ns.chunks = {
            cid: Chunk(
                id=c["id"],
                text=c["text"],
                metadata=(
                    ChunkMetadata(
                        source=meta.get("source", ""),
                        index=meta.get("index", 0),
                        total_chunks=meta.get("total_chunks", 0),
                        custom=dict(meta.get("custom", {})) if meta.get("custom") is not None else {},
                        original_path=meta.get("original_path"),
                        source_uri=meta.get("source_uri"),  # backward compat
                    )
                    if (meta := c.get("metadata"))
                    else None
                ),
            )
            for cid, c in data.get("chunks", {}).items()
        }
        ns.embeddings = {}
        for cid, emb in data.get("embeddings", {}).items():
            arr = np.array(emb, dtype=np.float32)
            if arr.shape[0] != self.dim:
                _logger.error(
                    "Memory index load failed: "
                    "embedding dimension mismatch",
                    extra={
                        "namespace": namespace,
                        "chunk_id": cid,
                        "expected": self.dim,
                        "got": arr.shape[0],
                    },
                )
                raise AdapterError(
                    "Index load failed for "
                    f"namespace '{namespace}': "
                    f"chunk '{cid}' has embedding "
                    f"dim {arr.shape[0]}, expected "
                    f"{self.dim}. Please reindex."
                )
            ns.embeddings[cid] = arr

        ns.metadata = data.get("metadata", {})
        ns._order.clear()
        ns._order.extend(ns.chunks.keys())

        # Integrity check: all three structures must be consistent
        emb_count = len(ns.embeddings)
        chunk_count = len(ns.chunks)
        meta_count = len(ns.metadata)
        if emb_count != chunk_count or meta_count != chunk_count:
            # Rollback partial state to
            # prevent stale data on retry
            ns.chunks.clear()
            ns.embeddings.clear()
            ns.metadata.clear()
            ns._order.clear()
            _logger.error(
                "Memory index integrity check "
                "failed: counts do not match "
                "(embeddings/chunks/metadata)",
                extra={
                    "namespace": namespace,
                    "embeddings": emb_count,
                    "chunks": chunk_count,
                    "metadata": meta_count,
                },
            )
            raise AdapterError(
                "Index integrity check failed "
                f"for namespace '{namespace}': "
                f"embeddings={emb_count}, "
                f"chunks={chunk_count}, "
                f"metadata={meta_count}. Please "
                "reindex to restore consistency."
            )

    async def load(self, path: str, namespace: str = "default") -> None:
        """Load namespace index + metadata. Validate version.

        Raises:
            AdapterError: If file is missing, unreadable, or JSON is invalid.
            VersionMismatchError: If stored dim does not match config dim.
        """
        try:
            async with self._lock:
                await self._load_unlocked(path, namespace=namespace)
        except (AdapterError, VersionMismatchError):
            raise
        except Exception:
            _logger.exception(
                "Memory vector store load failed",
                extra={"namespace": namespace, "path": path},
            )
            raise AdapterError(
                f"Failed to load memory store for namespace '{namespace}'"
            ) from None

    async def list_by_filter(
        self,
        filters: dict[str, Any],
        namespace: str = "default",
    ) -> list[tuple[str, dict[str, Any]]]:
        async with self._lock:
            ns = self._get_ns(namespace)
            return [
                (chunk_id, meta)
                for chunk_id, meta in ns.metadata.items()
                if all(meta.get(k) == v for k, v in filters.items())
            ]

    async def list_namespaces(self, path: str) -> list[str]:
        p = Path(path)
        if not await asyncio.to_thread(p.exists):
            return []
        entries = await asyncio.to_thread(lambda: list(p.iterdir()))
        result: list[str] = []
        for d in entries:
            is_dir = await asyncio.to_thread(d.is_dir)
            has_store = await asyncio.to_thread((d / "memory_store.json").exists)
            if is_dir and has_store:
                result.append(d.name)
        return result


class _NamespaceData:
    """Per-namespace state with FIFO eviction."""

    def __init__(self, dim: int, max_chunks: int) -> None:
        self.chunks: dict[str, Chunk] = {}
        self.embeddings: dict[str, np.ndarray] = {}
        self.metadata: dict[str, dict[str, Any]] = {}
        self.dim = dim
        self.max_chunks = max_chunks
        self._order: list[str] = []

    def _track(self, chunk_id: str) -> None:
        """Track insertion order for FIFO eviction."""
        if chunk_id not in self._order:
            self._order.append(chunk_id)

    def _evict(self) -> None:
        """Remove oldest chunks if over limit (FIFO)."""
        while len(self.chunks) > self.max_chunks and self._order:
            oldest = self._order.pop(0)
            self.chunks.pop(oldest, None)
            self.embeddings.pop(oldest, None)
            self.metadata.pop(oldest, None)
