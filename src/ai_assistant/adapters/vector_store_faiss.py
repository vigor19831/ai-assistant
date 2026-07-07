"""FAISS vector store adapter with multi-namespace persistence.

Saves per namespace:
- {namespace}.faiss  : binary FAISS index
- {namespace}.store.json : chunk metadata mapping

Load guard: if store.json is missing but index.faiss exists,
raise AdapterError to prevent silent empty-search corruption.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
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

# PATTERN: optional dependency wrapped at module level so factory.py
# can import this file without crashing when faiss-cpu is absent.
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
    meta_raw = data.get("metadata") or {}
    custom_raw = meta_raw.get("custom") or {}
    meta = ChunkMetadata(
        source=meta_raw.get("source", ""),
        index=meta_raw.get("index", 0),
        total_chunks=meta_raw.get("total_chunks", 0),
        custom=dict(custom_raw) if custom_raw is not None else {},
        original_path=meta_raw.get("original_path"),
        source_uri=meta_raw.get("source_uri"),
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
        """Add chunks with embeddings to a namespace.

        If the total would exceed max_chunks, raises AdapterError
        rather than silently evicting old data.
        """
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
                    _logger.error(
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

            # Reject if adding would exceed max_chunks
            projected = len(ns.chunks) + len(valid_chunks)
            max_chunks = self.config.max_chunks
            if projected > max_chunks:
                _logger.error(
                    "FAISS add would exceed max_chunks",
                    extra={
                        "namespace": namespace,
                        "current": len(ns.chunks),
                        "adding": len(valid_chunks),
                        "projected": projected,
                        "max_chunks": max_chunks,
                    },
                )
                raise AdapterError(
                    f"Cannot add {len(valid_chunks)} chunks to namespace "
                    f"'{namespace}': would exceed max_chunks ({max_chunks}). "
                    f"Current: {len(ns.chunks)}. "
                    f"Delete old chunks or increase max_chunks."
                )

            vectors = np.array(embeddings, dtype=np.float32)
            if self.config.metric.lower() == "cosine":
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                zero_mask = norms == 0
                if np.any(zero_mask):
                    _logger.warning(
                        "Zero-length embedding detected, skipping normalization",
                        extra={"namespace": namespace, "count": int(np.sum(zero_mask))},
                    )
                norms[zero_mask] = 1.0
                vectors = vectors / norms

            if ns.index is None:
                ns.index = self._make_index(dim)

            ns.index.add(vectors)  # type: ignore[union-attr]

            for chunk in valid_chunks:
                ns.chunks[ns.next_id] = chunk
                ns.next_id += 1

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
                norm = np.linalg.norm(q)
                if norm > 0:
                    q = q / norm
            distances, indices = ns.index.search(q, top_k)  # type: ignore[union-attr]
            results: list[Chunk] = []
            for idx in indices[0]:
                if idx == -1:
                    continue
                chunk = ns.chunks.get(int(idx))
                if chunk is not None:
                    results.append(chunk)
            return results

    def _rebuild_index(
        self, chunks: list[Chunk]
    ) -> tuple[Any, dict[int, Chunk], int]:
        """Rebuild FAISS index and chunk mapping from scratch."""
        dim = self.config.dim
        index = self._make_index(dim) if chunks else None
        chunks_dict: dict[int, Chunk] = {}
        next_id = 0

        if not chunks or index is None:
            return index, chunks_dict, next_id

        embeddings: list[list[float]] = []
        valid_chunks: list[Chunk] = []
        for chunk in chunks:
            if chunk.embedding is None:
                continue
            if len(chunk.embedding) != dim:
                _logger.error(
                    "Dimension mismatch during rebuild, skipping chunk",
                    extra={
                        "chunk_id": chunk.id,
                        "expected": dim,
                        "got": len(chunk.embedding),
                    },
                )
                continue
            embeddings.append(chunk.embedding)
            valid_chunks.append(chunk)

        if embeddings:
            vectors = np.array(embeddings, dtype=np.float32)
            if self.config.metric.lower() == "cosine":
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                zero_mask = norms == 0
                norms[zero_mask] = 1.0
                vectors = vectors / norms
            index.add(vectors)

        for chunk in valid_chunks:
            chunks_dict[next_id] = chunk
            next_id += 1

        return index, chunks_dict, next_id

    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        """Delete chunks by ID from a namespace and persist atomically.

        FAISS does not support true deletion without rebuilding the index.
        The rebuild and save are atomic under the namespace lock. If save
        fails, the in-memory state is rolled back by restoring the previous
        index and chunks dict.
        """
        if not chunk_ids:
            return

        async with self._lock:
            ns = self._get_ns(namespace)
            if ns.index is None:
                return

            # Snapshot current state for rollback
            old_index = ns.index
            old_chunks = dict(ns.chunks)
            old_next_id = ns.next_id

            ids_to_remove = set(chunk_ids)
            remaining = [
                chunk for chunk in ns.chunks.values() if chunk.id not in ids_to_remove
            ]
            new_index, new_chunks, next_id = self._rebuild_index(remaining)
            ns.index = new_index
            ns.chunks = new_chunks
            ns.next_id = next_id

            try:
                await self._save_unlocked(self.index_path, namespace)
            except Exception:
                _logger.exception(
                    "delete save failed, rolling back",
                    extra={"namespace": namespace},
                )
                # Restore in-memory state from snapshot
                ns.index = old_index
                ns.chunks = old_chunks
                ns.next_id = old_next_id
                raise

    def _atomic_write_faiss(self, index: Any, target_path: str) -> None:
        """Write FAISS index atomically via temp file + os.replace.

        Uses tempfile.mkstemp in the same directory as target_path
        to ensure the rename is on the same filesystem.
        """
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(target.parent),
            suffix=".tmp",
            prefix=f"{target.stem}_",
        )
        try:
            os.close(fd)
            faiss.write_index(index, tmp)
            os.replace(tmp, target)
            # Persist directory metadata (POSIX)
            try:
                dir_fd = os.open(
                    target.parent,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                )
            except OSError:
                pass  # Windows or filesystem without directory fsync support
            else:
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        except Exception:
            # Clean up temp file on failure; os.replace already removed it on success
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    async def save(self, path: str, namespace: str = "default") -> None:
        """Persist namespace index + metadata atomically.

        Writes both files into a temporary directory, then renames them
        into place. If a crash occurs between the two renames, the next
        load() will detect the inconsistency (ntotal != chunk_count) and
        raise AdapterError, requiring a reindex. This is intentional:
        detectable corruption is preferred over silent data loss.
        """
        async with self._lock:
            await self._save_unlocked(path, namespace)

    async def _save_unlocked(self, path: str, namespace: str) -> None:
        """Internal save — caller must hold self._lock."""
        ns = self._get_ns(namespace)
        if ns.index is None:
            return
        base = anyio.Path(path)
        await base.mkdir(parents=True, exist_ok=True)
        index_file = base / f"{namespace}.faiss"
        store_file = base / f"{namespace}.store.json"

        # Prepare data
        store_data = {
            "dim": self.config.dim,
            "metric": self.config.metric,
            "chunks": [_chunk_to_dict(c) for c in ns.chunks.values()],
        }

        # Write both files into a temp directory, then rename into place
        tmp_dir = base / f".{namespace}.tmp.{os.getpid()}"
        await tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_index = tmp_dir / f"{namespace}.faiss"
        tmp_store = tmp_dir / f"{namespace}.store.json"

        try:
            await asyncio.to_thread(
                self._atomic_write_faiss, ns.index, str(tmp_index)
            )
            await atomic_write(
                str(tmp_store), json.dumps(store_data, ensure_ascii=False)
            )
            # Sequential rename: small window of inconsistency.
            # If crash between renames, load() detects ntotal mismatch.
            await asyncio.to_thread(os.replace, str(tmp_index), str(index_file))
            await asyncio.to_thread(os.replace, str(tmp_store), str(store_file))
        except Exception:
            raise
        finally:
            # Clean up temp directory recursively
            with contextlib.suppress(OSError):
                if await tmp_dir.exists():
                    await asyncio.to_thread(shutil.rmtree, str(tmp_dir))

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
            except Exception:
                _logger.exception(
                    "FAISS load failed: unexpected error reading store.json",
                    extra={"namespace": namespace, "path": str(store_file)},
                )
                raise AdapterError(
                    f"Failed to read store.json for namespace '{namespace}'"
                ) from None

            if not isinstance(store_data, dict):
                _logger.error(
                    "FAISS load failed: store.json is not a JSON object",
                    extra={
                        "namespace": namespace,
                        "type": type(store_data).__name__,
                    },
                )
                raise AdapterError(
                    f"Invalid store.json for namespace '{namespace}': "
                    f"expected dict, got {type(store_data).__name__}"
                )

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

            stored_metric = store_data.get("metric")
            if (
                stored_metric is not None
                and stored_metric.lower() != self.config.metric.lower()
            ):
                _logger.error(
                    "FAISS metric mismatch: stored vs config",
                    extra={
                        "stored_metric": stored_metric,
                        "config_metric": self.config.metric,
                    },
                )
                raise VersionMismatchError(
                    "Reindex required: stored "
                    f"metric '{stored_metric}' != "
                    "config metric "
                    f"'{self.config.metric}'"
                )

            # Load FAISS index
            try:
                ns.index = await asyncio.to_thread(faiss.read_index, str(index_file))
            except Exception:
                _logger.exception(
                    "FAISS load failed: error reading index file",
                    extra={"namespace": namespace, "path": str(index_file)},
                )
                raise AdapterError(
                    f"Failed to read index for namespace '{namespace}'"
                ) from None

            # Rebuild chunk mapping
            ns.chunks.clear()
            ns.next_id = 0
            try:
                for chunk_data in store_data.get("chunks", []):
                    chunk = _chunk_from_dict(chunk_data)
                    ns.chunks[ns.next_id] = chunk
                    ns.next_id += 1
            except Exception:
                _logger.exception(
                    "FAISS load failed: chunk deserialization error",
                    extra={"namespace": namespace},
                )
                ns.index = None
                ns.chunks.clear()
                ns.next_id = 0
                raise AdapterError(
                    f"Failed to deserialize chunks for namespace '{namespace}'"
                ) from None

            # Integrity check: FAISS vector count must match metadata chunk count
            ntotal = ns.index.ntotal
            chunk_count = len(ns.chunks)
            if ntotal != chunk_count:
                # Rollback partial state to
                # prevent stale data on retry
                ns.index = None
                ns.chunks.clear()
                ns.next_id = 0
                _logger.error(
                    "FAISS index integrity check failed: "
                    "vector count does not match "
                    "metadata chunk count",
                    extra={
                        "namespace": namespace,
                        "ntotal": ntotal,
                        "chunks": chunk_count,
                    },
                )
                raise AdapterError(
                    "Index integrity check failed "
                    f"for namespace '{namespace}': "
                    f"FAISS has {ntotal} "
                    "vectors but metadata has "
                    f"{chunk_count} chunks. Please "
                    "reindex to restore consistency."
                )

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
        try:
            if not await base.exists():
                return []
        except OSError as exc:
            _logger.error(
                "list_namespaces: failed to check path existence",
                extra={"path": str(base), "error": str(exc)},
            )
            raise AdapterError(
                f"Failed to check index path {base}: {exc}"
            ) from exc

        namespaces: list[str] = []
        try:
            async for f in base.iterdir():
                try:
                    if not await f.is_file():
                        continue
                except OSError:
                    continue
                name = f.name
                # Detect valid namespace pairs: {namespace}.store.json + {namespace}.faiss
                if name.endswith(".store.json"):
                    ns_name = name[:-11]  # strip ".store.json"
                    faiss_file = base / f"{ns_name}.faiss"
                    try:
                        if await faiss_file.exists():
                            namespaces.append(ns_name)
                        else:
                            _logger.warning(
                                "Orphaned metadata file detected (no matching .faiss)",
                                extra={"namespace": ns_name, "path": str(f)},
                            )
                    except OSError as exc:
                        _logger.warning(
                            "list_namespaces: failed to check .faiss file",
                            extra={"namespace": ns_name, "error": str(exc)},
                        )
                elif name.endswith(".faiss"):
                    ns_name = name[:-6]  # strip ".faiss"
                    store_file = base / f"{ns_name}.store.json"
                    try:
                        if not await store_file.exists():
                            _logger.warning(
                                "Orphaned FAISS index file detected (no matching store.json)",
                                extra={"namespace": ns_name, "path": str(f)},
                            )
                    except OSError as exc:
                        _logger.warning(
                            "list_namespaces: failed to check .store.json file",
                            extra={"namespace": ns_name, "error": str(exc)},
                        )
        except OSError as exc:
            _logger.error(
                "list_namespaces: failed to iterate directory",
                extra={"path": str(base), "error": str(exc)},
            )
            raise AdapterError(
                f"Failed to list namespaces in {base}: {exc}"
            ) from exc
        return sorted(set(namespaces))

    async def shutdown(self) -> None:
        """No-op — FAISS index is in-memory, persistence is explicit via save()."""
        pass
