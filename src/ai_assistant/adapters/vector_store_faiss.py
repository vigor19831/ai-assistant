"""FAISS vector store with namespace (collection) support."""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    import faiss

    _FAISS_AVAILABLE = True
except ImportError:
    faiss: Any = None  # type: ignore[assignment, no-redef]
    _FAISS_AVAILABLE = False

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.ports.vector_store import IVectorStore
from ai_assistant.core.registry import register

__all__ = ["FaissVectorStore"]


if _FAISS_AVAILABLE:

    @register("vector_store", "faiss")
    class FaissVectorStore(IVectorStore):
        """Thread-safe FAISS vector store with multi-namespace support.

        Each namespace is an isolated index stored under:
            {path}/{namespace}/index.faiss
            {path}/{namespace}/index_meta.json
            {path}/{namespace}/store.json
        """

        def __init__(self, config: Any) -> None:
            super().__init__(config)
            self.dim: int = config.dim
            self.metric: str = config.metric
            self._namespaces: dict[str, _NamespaceData] = {}
            self._lock = asyncio.Lock()

        def _create_index(self) -> faiss.Index:
            if self.metric == "ip":
                return faiss.IndexFlatIP(self.dim)
            return faiss.IndexFlatL2(self.dim)

        def _get_ns(self, name: str) -> _NamespaceData:
            if name not in self._namespaces:
                self._namespaces[name] = _NamespaceData(
                    index=None,
                    chunks={},
                    metadata={},
                    id_map={},
                    next_id=0,
                )
            return self._namespaces[name]

        def _validate_dim(self, embedding: list[float], chunk_id: str = "") -> None:
            if len(embedding) != self.dim:
                raise AdapterError(
                    f"Dimension mismatch in FAISS add: expected {self.dim}, "
                    f"got {len(embedding)} (chunk_id={chunk_id!r}). "
                    f"Check embedder config.dim vs vector_store config.dim."
                )

        async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
            if not chunks:
                return
            async with self._lock:
                ns = self._get_ns(namespace)
                if ns.index is None:
                    ns.index = self._create_index()

                embeddings: list[list[float]] = []
                valid_chunks: list[Chunk] = []
                for c in chunks:
                    if c.embedding is None:
                        continue
                    self._validate_dim(c.embedding, c.id)
                    embeddings.append(c.embedding)
                    valid_chunks.append(c)

                if not embeddings:
                    return

                vectors = np.array(embeddings, dtype=np.float32)
                start_id = ns.next_id
                ns.index.add(vectors)

                for i, chunk in enumerate(valid_chunks):
                    faiss_id = start_id + i
                    ns.chunks[faiss_id] = chunk
                    ns.id_map[chunk.id] = faiss_id
                    meta: dict[str, Any] = {}
                    if chunk.metadata is not None:
                        meta = chunk.metadata.custom.copy()
                        meta["source"] = chunk.metadata.source
                        meta["index"] = chunk.metadata.index
                    ns.metadata[chunk.id] = meta

                ns.next_id += len(valid_chunks)

        async def search(
            self,
            query_embedding: list[float],
            top_k: int = 5,
            namespace: str = "default",
        ) -> list[Chunk]:
            self._validate_dim(query_embedding, "<query>")
            async with self._lock:
                if namespace not in self._namespaces:
                    return []
                ns = self._namespaces[namespace]
                if ns.index is None or ns.index.ntotal == 0:
                    return []
                q = np.array([query_embedding], dtype=np.float32)
                distances, indices = ns.index.search(q, top_k)
                results: list[Chunk] = []
                for idx in indices[0]:
                    if idx < 0:
                        continue
                    chunk = ns.chunks.get(int(idx))
                    if chunk:
                        results.append(chunk)
                return results

        async def delete(
            self, chunk_ids: list[str], namespace: str = "default"
        ) -> None:
            async with self._lock:
                ns = self._get_ns(namespace)
                ids_to_remove = set(chunk_ids)
                remaining: list[Chunk] = []
                for fid, chunk in ns.chunks.items():
                    if chunk.id not in ids_to_remove and chunk.embedding:
                        remaining.append(chunk)

                ns.index = self._create_index()
                ns.chunks.clear()
                ns.id_map.clear()
                ns.metadata = {
                    k: v for k, v in ns.metadata.items() if k not in ids_to_remove
                }
                ns.next_id = 0

                if not remaining:
                    return

                embeddings: list[list[float]] = []
                valid_chunks: list[Chunk] = []
                for c in remaining:
                    if c.embedding is None:
                        continue
                    self._validate_dim(c.embedding, c.id)
                    embeddings.append(c.embedding)
                    valid_chunks.append(c)

                if not embeddings:
                    return

                vectors = np.array(embeddings, dtype=np.float32)
                start_id = ns.next_id
                ns.index.add(vectors)

                for i, chunk in enumerate(valid_chunks):
                    faiss_id = start_id + i
                    ns.chunks[faiss_id] = chunk
                    ns.id_map[chunk.id] = faiss_id
                    meta: dict[str, Any] = {}
                    if chunk.metadata is not None:
                        meta = chunk.metadata.custom.copy()
                        meta["source"] = chunk.metadata.source
                        meta["index"] = chunk.metadata.index
                    ns.metadata[chunk.id] = meta

                ns.next_id += len(valid_chunks)

        async def save(self, path: str, namespace: str = "default") -> None:
            async with self._lock:
                ns = self._get_ns(namespace)
                if ns.index is None:
                    return
                p = Path(path) / namespace
                p.mkdir(parents=True, exist_ok=True)
                faiss.write_index(ns.index, str(p / "index.faiss"))

                meta = {
                    "version": "1.0",
                    "embedder_model": getattr(self.config, "embedder_model", "unknown"),
                    "embedder_dim": self.dim,
                    "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    "chunk_count": len(ns.chunks),
                    "metric": self.metric,
                }
                await atomic_write(p / "index_meta.json", json.dumps(meta, indent=2))

                store = {
                    "chunks": {
                        str(k): {
                            "id": c.id,
                            "text": c.text,
                            "embedding": c.embedding,
                            "metadata": (
                                {
                                    "source": c.metadata.source,
                                    "index": c.metadata.index,
                                    "total_chunks": c.metadata.total_chunks,
                                    "created_at": c.metadata.created_at,
                                    "custom": c.metadata.custom,
                                }
                                if c.metadata
                                else None
                            ),
                        }
                        for k, c in ns.chunks.items()
                    },
                    "metadata": ns.metadata,
                    "id_map": ns.id_map,
                    "next_id": ns.next_id,
                }
                await atomic_write(p / "store.json", json.dumps(store, indent=2))

        async def load(self, path: str, namespace: str = "default") -> None:
            p = Path(path) / namespace
            index_path = p / "index.faiss"
            if not await asyncio.to_thread(index_path.exists):
                return

            index = await asyncio.to_thread(faiss.read_index, str(index_path))

            meta_path = p / "index_meta.json"
            meta = None
            if await asyncio.to_thread(meta_path.exists):
                meta_text = await asyncio.to_thread(meta_path.read_text)
                meta = json.loads(meta_text)
                stored_dim = meta.get("embedder_dim")
                if stored_dim is not None and stored_dim != self.dim:
                    raise VersionMismatchError(
                        f"Reindex required: stored dim {stored_dim} "
                        f"!= config dim {self.dim}"
                    )

            store_path = p / "store.json"
            store = None
            if await asyncio.to_thread(store_path.exists):
                store_text = await asyncio.to_thread(store_path.read_text)
                store = json.loads(store_text)

            async with self._lock:
                ns = self._get_ns(namespace)
                ns.chunks.clear()
                ns.metadata.clear()
                ns.id_map.clear()
                ns.index = index
                if store:
                    for k, v in store.get("chunks", {}).items():
                        m = v.get("metadata")
                        chunk_meta = (
                            ChunkMetadata(
                                source=m.get("source", ""),
                                index=m.get("index", 0),
                                total_chunks=m.get("total_chunks", 0),
                                created_at=m.get("created_at", ""),
                                custom=m.get("custom", {}),
                            )
                            if m
                            else None
                        )
                        ns.chunks[int(k)] = Chunk(
                            id=v["id"],
                            text=v["text"],
                            embedding=v.get("embedding"),
                            metadata=chunk_meta,
                        )
                    ns.metadata = store.get("metadata", {})
                    ns.id_map = {
                        str(k): int(v) for k, v in store.get("id_map", {}).items()
                    }
                    ns.next_id = store.get("next_id", 0)

        async def list_by_filter(
            self,
            filters: dict[str, Any],
            namespace: str = "default",
        ) -> list[tuple[str, dict[str, Any]]]:
            async with self._lock:
                if namespace not in self._namespaces:
                    return []
                ns = self._namespaces[namespace]
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
                has_index = await asyncio.to_thread((d / "index.faiss").exists)
                if is_dir and has_index:
                    result.append(d.name)
            return result

    class _NamespaceData:
        """Internal per-namespace state container."""

        def __init__(
            self,
            index: faiss.Index | None,
            chunks: dict[int, Chunk],
            metadata: dict[str, dict[str, Any]],
            id_map: dict[str, int],
            next_id: int,
        ) -> None:
            self.index = index
            self.chunks = chunks
            self.metadata = metadata
            self.id_map = id_map
            self.next_id = next_id

else:

    @register("vector_store", "faiss")
    class FaissVectorStore(IVectorStore):  # type: ignore[no-redef]
        """Explicitly unavailable — raises on any operation."""

        def __init__(self, config: Any) -> None:
            super().__init__(config)
            raise ImportError(
                "faiss-cpu is not installed but "
                "vector_store.provider='faiss'. "
                "Install: pip install faiss-cpu"
            )
