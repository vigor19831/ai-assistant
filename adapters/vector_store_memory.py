"""In-memory vector store with namespace support and strict relevance filtering."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np

from core.domain.documents import Chunk
from core.io_utils import atomic_write
from core.ports.vector_store import IVectorStore
from core.registry import register


@register("vector_store", "memory")
class MemoryVectorStore(IVectorStore):
    """Simple in-memory vector store with multi-namespace support.

    Uses cosine similarity with strict threshold to prevent irrelevant results.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.dim: int = config.dim
        self._namespaces: dict[str, _NamespaceData] = {}
        self._lock = asyncio.Lock()

    def _get_ns(self, name: str) -> _NamespaceData:
        if name not in self._namespaces:
            self._namespaces[name] = _NamespaceData(
                chunks={},
                embeddings={},
                metadata={},
                dim=self.dim,
            )
        return self._namespaces[name]

    def _normalize(self, v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

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
                meta = (
                    chunk.metadata.custom
                    if chunk.metadata and chunk.metadata.custom
                    else {}
                )
                meta["source"] = chunk.metadata.source if chunk.metadata else ""
                meta["index"] = chunk.metadata.index if chunk.metadata else 0
                ns.metadata[chunk.id] = meta

    async def search(
        self, query_embedding: list[float], top_k: int = 5, namespace: str = "default"
    ) -> list[Chunk]:
        """Search for relevant chunks with strict similarity threshold.

        Returns empty list if no chunks meet the relevance threshold,
        preventing irrelevant results from being returned.
        """
        async with self._lock:
            ns = self._get_ns(namespace)
            if not ns.embeddings:
                return []

            try:
                q = self._normalize(np.array(query_embedding, dtype=np.float32))
                ids = list(ns.embeddings.keys())
                matrix = np.stack([ns.embeddings[i] for i in ids])
                scores = matrix @ q
            except Exception:
                return []

            # Dynamic threshold from config
            raw_threshold = getattr(self.config, "relevance_threshold", 0.3)
            try:
                threshold = float(raw_threshold)
            except (TypeError, ValueError):
                threshold = 0.3

            # Filter by similarity threshold - STRICT
            valid_indices = np.where(scores >= threshold)[0]
            if len(valid_indices) == 0:
                return []

            # Sort valid results by score descending
            valid_scores = scores[valid_indices]
            sorted_order = np.argsort(valid_scores)[::-1]
            top_indices = valid_indices[sorted_order[:top_k]]

            return [ns.chunks[ids[i]] for i in top_indices]

    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        async with self._lock:
            ns = self._get_ns(namespace)
            for cid in chunk_ids:
                ns.chunks.pop(cid, None)
                ns.embeddings.pop(cid, None)
                ns.metadata.pop(cid, None)

    async def save(self, path: str, namespace: str = "default") -> None:
        p = Path(path) / namespace
        p.parent.mkdir(parents=True, exist_ok=True)
        ns = self._get_ns(namespace)
        data = {
            "dim": ns.dim,
            "chunks": {
                cid: {"id": c.id, "text": c.text} for cid, c in ns.chunks.items()
            },
            "embeddings": {cid: emb.tolist() for cid, emb in ns.embeddings.items()},
            "metadata": ns.metadata,
        }
        await atomic_write(p / "memory_store.json", json.dumps(data, indent=2))

    async def load(self, path: str, namespace: str = "default") -> None:
        p = Path(path) / namespace / "memory_store.json"
        if not await asyncio.to_thread(p.exists):
            return
        data_text = await asyncio.to_thread(p.read_text)
        data = json.loads(data_text)
        async with self._lock:
            ns = self._get_ns(namespace)
            ns.dim = data.get("dim", self.dim)
            ns.chunks = {
                cid: Chunk(id=c["id"], text=c["text"])
                for cid, c in data.get("chunks", {}).items()
            }
            ns.embeddings = {
                cid: np.array(emb, dtype=np.float32)
                for cid, emb in data.get("embeddings", {}).items()
            }
            ns.metadata = data.get("metadata", {})

    async def list_by_filter(
        self, filter: dict[str, Any], namespace: str = "default"
    ) -> list[tuple[str, dict[str, Any]]]:
        async with self._lock:
            ns = self._get_ns(namespace)
            results: list[tuple[str, dict[str, Any]]] = []
            for chunk_id, meta in ns.metadata.items():
                match = all(meta.get(k) == v for k, v in filter.items())
                if match:
                    results.append((chunk_id, meta))
            return results

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
    def __init__(
        self,
        chunks: dict[str, Chunk],
        embeddings: dict[str, np.ndarray],
        metadata: dict[str, dict[str, Any]],
        dim: int,
    ) -> None:
        self.chunks = chunks
        self.embeddings = embeddings
        self.metadata = metadata
        self.dim = dim
