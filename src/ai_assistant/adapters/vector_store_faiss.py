"""FAISS vector store adapter with multi-namespace persistence.

Saves per namespace:
- {namespace}.faiss  : binary FAISS index
- {namespace}.store.json : chunk metadata mapping

Load guard: if store.json is missing but index.faiss exists,
raise AdapterError to prevent silent empty-search corruption.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import anyio
import numpy as np

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import VectorStoreConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.vector_store import IVectorStore

try:
    import faiss
except ImportError:
    faiss = None  # type: ignore[assignment, no-redef]

__all__ = ["FaissVectorStore"]

_logger = get_logger("adapters.vector_store_faiss")


class _NamespaceData:
    """Per-namespace runtime state."""

    def __init__(self) -> None:
        self.index: Any = None
        self.chunks: dict[int, Chunk] = {}
        self.next_id: int = 0


def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """Serialize Chunk to dict (strict, no extra fields)."""
    meta = chunk.metadata
    return {
        "id": chunk.id,
        "text": chunk.text,
        "embedding": chunk.embedding,
        "metadata": {
            "source": meta.source if meta else "",
            "index": meta.index if meta else 0,
            "total_chunks": meta.total_chunks if meta else 0,
            "custom": meta.custom if meta else {},
            "original_path": meta.original_path if meta else None,
            "source_uri": meta.source_uri if meta else None,
        },
    }


def _chunk_from_dict(data: dict[str, Any]) -> Chunk:
    """Deserialize dict to Chunk (strict, matches domain model)."""
    meta_raw = data.get("metadata", {})
    meta = ChunkMetadata(
        source=meta_raw.get("source", ""),
        index=meta_raw.get("index", 0),
        total_chunks=meta_raw.get("total_chunks", 0),
        custom=meta_raw.get("custom", {}),
        original_path=meta_raw.get("original_path"),
        source_uri=meta_raw.get("source_uri"),  # backward compat: old indices have None
    )
    return Chunk(
        id=data["id"],
        text=data["text"],
        embedding=data.get("embedding"),
        metadata=meta,
    )


@register("vector_store", "faiss")
class FaissVectorStore(IVectorStore):
    """FAISS-backed vector store with namespace support."""

    def __init__(self, config: VectorStoreConfigData) -> None:
        super().__init__(config)
        self._namespaces: dict[str, _NamespaceData] = {}
        self._lock = asyncio.Lock()
        if faiss is None:
            raise ImportError(
                "faiss-cpu is not installed but vector_store.provider='faiss'"
            )

    @property
    def index_path(self) -> str:
        return self.config.index_path

    def _get_ns(self, namespace: str) -> _NamespaceData:
        if namespace not in self._namespaces:
            self._namespaces[namespace] = _NamespaceData()
        return self._namespaces[namespace]

    def _make_index(self, dim: int) -> Any:
        metric = self.config.metric.lower()
        if metric == "ip":
            return faiss.IndexFlatIP(dim)
        if metric == "cosine":
            # Normalize + inner product = cosine similarity
            return faiss.IndexFlatIP(dim)
        return faiss.IndexFlatL2(dim)

    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Add chunks with embeddings to a namespace."""
        if not chunks:
            return
        async with self._lock:
            ns = self._get_ns(namespace)
            dim = self.config.dim

            embeddings: list[list[float]] = []
            valid_chunks: list[Chunk] = []
            for chunk in chunks:
                if chunk.embedding is None:
                    continue
                if len(chunk.embedding) != dim:
                    _logger.exception(
                        "Dimension mismatch in FAISS add",
                        extra={
                            "expected": dim,
                            "got": len(chunk.embedding),
                            "chunk_id": chunk.id,
                        },
                    )
                    raise AdapterError(
                        f"Dimension mismatch in FAISS add: expected {dim}, "
                        f"got {len(chunk.embedding)} ({chunk.id})"
                    )
                embeddings.append(chunk.embedding)
                valid_chunks.append(chunk)

            if not embeddings:
                return

            vectors = np.array(embeddings, dtype=np.float32)
            if self.config.metric.lower() == "cosine":
                faiss.normalize_L2(vectors)

            if ns.index is None:
                ns.index = self._make_index(dim)

            ns.index.add(vectors)  # type: ignore[union-attr]

            for chunk in valid_chunks:
                ns.chunks[ns.next_id] = chunk
                ns.next_id += 1

            # FIFO eviction if max_chunks exceeded
            max_chunks = self.config.max_chunks
            while len(ns.chunks) > max_chunks:
                oldest = min(ns.chunks.keys())
                del ns.chunks[oldest]

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        namespace: str = "default",
    ) -> list[Chunk]:
        """Search by embedding in a namespace."""
        async with self._lock:
            ns = self._get_ns(namespace)
            if ns.index is None or ns.index.ntotal == 0:
                return []
            dim = self.config.dim
            if len(query_embedding) != dim:
                _logger.error(
                    "Dimension mismatch in FAISS search",
                    extra={
                        "expected": dim,
                        "got": len(query_embedding),
                    },
                )
                raise AdapterError(
                    f"Dimension mismatch in FAISS search: expected {dim}, "
                    f"got {len(query_embedding)}"
                )
            q = np.array([query_embedding], dtype=np.float32)
            if self.config.metric.lower() == "cosine":
                faiss.normalize_L2(q)
            distances, indices = ns.index.search(q, top_k)  # type: ignore[union-attr]
            results: list[Chunk] = []
            for idx in indices[0]:
                if idx == -1:
                    continue
                chunk = ns.chunks.get(int(idx))
                if chunk is not None:
                    results.append(chunk)
            return results

    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        """Delete chunks by ID from a namespace.

        FAISS does not support true deletion without rebuilding the index.
        We rebuild the index from remaining chunks.
        """
        async with self._lock:
            ns = self._get_ns(namespace)
            if ns.index is None:
                return
            ids_to_remove = set(chunk_ids)
            remaining = [
                chunk for chunk in ns.chunks.values() if chunk.id not in ids_to_remove
            ]
            ns.chunks.clear()
            ns.next_id = 0
            ns.index = None
            # Release lock before calling add() to avoid deadlock
            # add() will reacquire the lock

        if remaining:
            await self.add(remaining, namespace=namespace)

    async def save(self, path: str, namespace: str = "default") -> None:
        """Persist namespace index + metadata."""
        async with self._lock:
            ns = self._get_ns(namespace)
            if ns.index is None:
                return
            base = anyio.Path(path)
            await base.mkdir(parents=True, exist_ok=True)
            index_file = base / f"{namespace}.faiss"
            store_file = base / f"{namespace}.store.json"

            # Save FAISS index
            await asyncio.to_thread(faiss.write_index, ns.index, str(index_file))

            # Save metadata store
            store_data = {
                "dim": self.config.dim,
                "metric": self.config.metric,
                "chunks": [_chunk_to_dict(c) for c in ns.chunks.values()],
            }
            await atomic_write(
                str(store_file), json.dumps(store_data, ensure_ascii=False)
            )

    async def load(self, path: str, namespace: str = "default") -> None:
        """Load namespace index + metadata. Validate version.

        Raises:
            AdapterError: If store.json is missing but index.faiss exists,
                indicating corrupted or incomplete index state.
            VersionMismatchError: If stored dim does not match config dim.
        """
        base = anyio.Path(path)
        index_file = base / f"{namespace}.faiss"
        store_file = base / f"{namespace}.store.json"

        # GUARD: store.json must exist if we expect to load meaningful data.
        # Loading index.faiss without store.json leaves ns.chunks empty,
        # causing silent empty search results — a data corruption scenario.
        if not await store_file.exists():
            if await index_file.exists():
                _logger.error(
                    "FAISS load failed: store.json missing for namespace "
                    "(index.faiss exists but metadata is absent). "
                    "This indicates index corruption or incomplete migration.",
                    extra={
                        "namespace": namespace,
                        "path": str(base),
                    },
                )
                raise AdapterError(
                    f"Index metadata missing for namespace '{namespace}': "
                    f"{store_file.name} not found. "
                    f"Please reindex to restore consistency."
                )
            # Neither file exists — nothing to load, clean state.
            return

        # If we reach here, store_file exists. index_file should also exist.
        if not await index_file.exists():
            _logger.error(
                "FAISS load failed: index.faiss missing for namespace "
                "(store.json exists but index is absent).",
                extra={
                    "namespace": namespace,
                    "path": str(base),
                },
            )
            raise AdapterError(
                f"Index file missing for namespace '{namespace}': "
                f"{index_file.name} not found. "
                f"Please reindex to restore consistency."
            )

        async with self._lock:
            ns = self._get_ns(namespace)

            # Load metadata first to validate before touching the index
            try:
                store_text = await store_file.read_text(encoding="utf-8")
                store_data = json.loads(store_text)
            except json.JSONDecodeError as exc:
                _logger.error(
                    "FAISS load failed: invalid JSON in store.json",
                    extra={
                        "namespace": namespace,
                        "error": str(exc),
                    },
                )
                raise AdapterError(
                    f"Invalid store.json for namespace '{namespace}': {exc}"
                ) from exc

            stored_dim = store_data.get("dim")
            if stored_dim is not None and stored_dim != self.config.dim:
                _logger.error(
                    "FAISS dimension mismatch: stored vs config",
                    extra={
                        "stored_dim": stored_dim,
                        "config_dim": self.config.dim,
                    },
                )
                raise VersionMismatchError(
                    f"Reindex required: stored dim {stored_dim} != "
                    f"config dim {self.config.dim}"
                )

            # Load FAISS index
            ns.index = await asyncio.to_thread(faiss.read_index, str(index_file))

            # Rebuild chunk mapping
            ns.chunks.clear()
            ns.next_id = 0
            for chunk_data in store_data.get("chunks", []):
                chunk = _chunk_from_dict(chunk_data)
                ns.chunks[ns.next_id] = chunk
                ns.next_id += 1

            _logger.info(
                "FAISS loaded namespace",
                extra={
                    "namespace": namespace,
                    "chunks": len(ns.chunks),
                    "path": str(base),
                },
            )

    async def list_by_filter(
        self,
        filters: dict[str, Any],
        namespace: str = "default",
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return (chunk_id, metadata) matching ALL filters key-values."""
        async with self._lock:
            ns = self._get_ns(namespace)
            results: list[tuple[str, dict[str, Any]]] = []
            for chunk in ns.chunks.values():
                meta = chunk.metadata
                meta_dict = {
                    "source": meta.source if meta else "",
                    "index": meta.index if meta else 0,
                    "total_chunks": meta.total_chunks if meta else 0,
                    **(meta.custom if meta else {}),
                }
                if all(meta_dict.get(k) == v for k, v in filters.items()):
                    results.append((chunk.id, meta_dict))
            return results

    async def list_namespaces(self, path: str) -> list[str]:
        """Return list of available namespace names from store.json files."""
        base = anyio.Path(path)
        if not await base.exists():
            return []
        namespaces: list[str] = []
        async for f in base.iterdir():
            if await f.is_file() and f.suffixes == [".store", ".json"]:
                namespaces.append(f.stem.split(".")[0])
            elif await f.is_file() and f.suffix == ".faiss":
                # Also detect orphaned index files (no store.json)
                ns_name = f.stem
                store_file = base / f"{ns_name}.store.json"
                if await store_file.exists():
                    namespaces.append(ns_name)
        return sorted(set(namespaces))

    async def shutdown(self) -> None:
        """No-op — FAISS index is in-memory, persistence is explicit via save()."""
        pass
