"""BM25 lexical index -- exact-term retrieval over chunk texts.

Pure-stdlib adapter (no new dependencies, architecture 11.2).
Mirrors the IVectorStore lifecycle per namespace; the vector store
stays the inventory authority. Disk format: one JSON file per
namespace, derived data -- rebuild by reindexing.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_assistant.adapters._registry import register
from ai_assistant.core.constants import DOC_DATE_KEY
from ai_assistant.core.domain.configs import LexicalIndexConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.domain.pipeline import DateFilter
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.lexical_index import ILexicalIndex

__all__ = ["LexicalBm25Index"]

_FORMAT_VERSION = 1
_BM25_K1 = 1.5  # Term-frequency saturation.
_BM25_B = 0.75  # Document-length normalization.
_WORD_RE = re.compile(r"\w+")  # Unicode-aware: Cyrillic included.

_logger = get_logger("adapters.lexical_bm25")


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens."""
    return _WORD_RE.findall(text.lower())


def _read_namespace_file(file: Path) -> str | None:
    """Read a namespace index file; None when it does not exist yet.

    Sync pathlib IO -- always called via asyncio.to_thread.
    """
    if not file.is_file():
        return None
    return file.read_text(encoding="utf-8")


def _list_namespace_files(path: str) -> list[str]:
    """Return sorted namespace names for *.json files under path.

    Sync pathlib IO -- always called via asyncio.to_thread.
    """
    directory = Path(path)
    if not directory.is_dir():
        return []
    return sorted(item.stem for item in directory.glob("*.json"))


@dataclass
class _NamespaceData:
    """Search statistics for one namespace, derived from chunks."""

    chunks: dict[str, Chunk]
    tf: dict[str, Counter[str]]  # chunk id -> term counts
    df: Counter[str]  # term -> number of chunks containing it
    lengths: dict[str, int]  # chunk id -> token count


def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """Serialize a Chunk for the JSON disk format (drift #5 pattern)."""
    md = chunk.metadata
    return {
        "id": chunk.id,
        "text": chunk.text,
        "metadata": None
        if md is None
        else {
            "source": md.source,
            "index": md.index,
            "total_chunks": md.total_chunks,
            "custom": md.custom,
            "original_path": md.original_path,
            "source_uri": md.source_uri,
            "last_modified": md.last_modified,
        },
    }


def _chunk_from_dict(record: dict[str, Any]) -> Chunk:
    """Deserialize a Chunk from the JSON disk format."""
    raw_md = record.get("metadata")
    metadata = None
    if raw_md is not None:
        metadata = ChunkMetadata(
            source=raw_md["source"],
            index=raw_md["index"],
            total_chunks=raw_md["total_chunks"],
            custom=raw_md.get("custom") or {},
            original_path=raw_md.get("original_path"),
            source_uri=raw_md.get("source_uri"),
            last_modified=raw_md.get("last_modified"),
        )
    return Chunk(id=record["id"], text=record["text"], metadata=metadata)


@register("lexical_index", "bm25")
class LexicalBm25Index(ILexicalIndex):
    """In-memory BM25 with JSON persistence per namespace."""

    def __init__(self, config: LexicalIndexConfigData) -> None:
        super().__init__(config)
        self._namespaces: dict[str, _NamespaceData] = {}
        # Same documented race as MemoryVectorStore/FaissVectorStore
        # (architecture 11.3): background reindex vs API search.
        self._lock = asyncio.Lock()

    @property
    def index_path(self) -> str:
        return self.config.index_path

    def _file_path(self, path: str, namespace: str) -> Path:
        return Path(path) / f"{namespace}.json"

    def _ensure_namespace_locked(self, namespace: str) -> _NamespaceData:
        data = self._namespaces.get(namespace)
        if data is None:
            data = _NamespaceData(chunks={}, tf={}, df=Counter(), lengths={})
            self._namespaces[namespace] = data
        return data

    def _insert_locked(self, data: _NamespaceData, chunk: Chunk) -> None:
        tokens = _tokenize(chunk.text)
        counts = Counter(tokens)
        data.chunks[chunk.id] = chunk
        data.tf[chunk.id] = counts
        data.lengths[chunk.id] = len(tokens)
        for token in counts:
            data.df[token] += 1

    def _remove_locked(self, data: _NamespaceData, chunk_id: str) -> Chunk | None:
        counts = data.tf.pop(chunk_id, None)
        if counts is None:
            return None
        chunk = data.chunks.pop(chunk_id)
        del data.lengths[chunk_id]
        for token in counts:
            data.df[token] -= 1
            if data.df[token] <= 0:
                del data.df[token]
        return chunk

    def _search_locked(
        self,
        query_text: str,
        top_k: int,
        namespace: str,
        date_filter: DateFilter | None = None,
    ) -> list[Chunk]:
        if top_k < 1:
            return []
        data = self._namespaces.get(namespace)
        if data is None or not data.chunks:
            return []
        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return []
        n_docs = len(data.chunks)
        avg_len = sum(data.lengths.values()) / n_docs
        scores: dict[str, float] = {}
        for token in query_tokens:
            df = data.df[token]
            if df == 0:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for chunk_id, tf_map in data.tf.items():
                tf = tf_map.get(token)
                if not tf:
                    continue
                if date_filter is not None and not date_filter.matches(
                    self._doc_date_of(data.chunks[chunk_id])
                ):
                    continue
                norm = 1.0 - _BM25_B + _BM25_B * data.lengths[chunk_id] / avg_len
                denom = tf + _BM25_K1 * norm
                scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                    idf * tf * (_BM25_K1 + 1.0) / denom
                )
        if not scores:
            return []
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return [data.chunks[chunk_id] for chunk_id, _ in ranked[:top_k]]

    @staticmethod
    def _doc_date_of(chunk: Chunk) -> str | None:
        if chunk.metadata is None:
            return None
        return chunk.metadata.custom.get(DOC_DATE_KEY)

    async def _save_locked(
        self, namespace: str, data: _NamespaceData, path: str | None = None
    ) -> None:
        base = path if path is not None else self.config.index_path
        file = self._file_path(base, namespace)
        payload = {
            "format_version": _FORMAT_VERSION,
            "chunks": [_chunk_to_dict(c) for c in data.chunks.values()],
        }
        try:
            await atomic_write(file, json.dumps(payload, ensure_ascii=False))
        except OSError as exc:
            _logger.exception(
                "lexical index save failed", extra={"file": str(file)}
            )
            raise AdapterError(f"failed to write lexical index {file}") from exc

    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        if not chunks:
            return
        async with self._lock:
            data = self._ensure_namespace_locked(namespace)
            for chunk in chunks:
                if chunk.id in data.chunks:
                    self._remove_locked(data, chunk.id)  # idempotent replace
                self._insert_locked(data, chunk)

    async def upsert(self, chunks: list[Chunk], namespace: str = "default") -> None:
        if not chunks:
            return
        async with self._lock:
            data = self._ensure_namespace_locked(namespace)
            sources = {
                c.metadata.source for c in chunks if c.metadata is not None
            }
            new_ids = {c.id for c in chunks}
            old_ids = [
                chunk_id
                for chunk_id, chunk in data.chunks.items()
                if chunk_id not in new_ids
                and chunk.metadata is not None
                and chunk.metadata.source in sources
            ]
            # Add before delete: on failure the old chunks remain (drift #88).
            for chunk in chunks:
                if chunk.id in data.chunks:
                    self._remove_locked(data, chunk.id)
                self._insert_locked(data, chunk)
            for chunk_id in old_ids:
                self._remove_locked(data, chunk_id)

    async def search(
        self,
        query_text: str,
        top_k: int = 5,
        namespace: str = "default",
        date_filter: DateFilter | None = None,
    ) -> list[Chunk]:
        async with self._lock:
            return self._search_locked(query_text, top_k, namespace, date_filter)

    async def list_by_filter(
        self,
        filters: dict[str, str | int | float | bool | None],
        namespace: str = "default",
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return (chunk_id, metadata) matching ALL filter key-values.

        Read-only: an unknown namespace returns [] and is never
        created. Metadata mirrors the IVectorStore shape: custom
        keys first, typed fields overwrite (drift #120 parity),
        plus the nested "custom" dict.
        """
        async with self._lock:
            data = self._namespaces.get(namespace)
            if data is None:
                return []
            results: list[tuple[str, dict[str, Any]]] = []
            for chunk_id, chunk in data.chunks.items():
                md = chunk.metadata
                if md is None:
                    if filters:
                        continue
                    results.append((chunk_id, {}))
                    continue
                meta: dict[str, Any] = {
                    **md.custom,
                    "custom": md.custom,
                    "source": md.source,
                    "index": md.index,
                    "total_chunks": md.total_chunks,
                    "source_uri": md.source_uri,
                    "original_path": md.original_path,
                    "last_modified": md.last_modified,
                }
                if all(meta.get(key) == value for key, value in filters.items()):
                    results.append((chunk_id, meta))
            return results

    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        if not chunk_ids:
            return
        async with self._lock:
            data = self._namespaces.get(namespace)
            if data is None:
                return
            removed: list[Chunk] = []
            for chunk_id in chunk_ids:
                chunk = self._remove_locked(data, chunk_id)
                if chunk is not None:
                    removed.append(chunk)
            if not removed:
                return
            became_empty = not data.chunks
            try:
                if became_empty:
                    file = self._file_path(self.config.index_path, namespace)
                    await asyncio.to_thread(file.unlink, missing_ok=True)
                    del self._namespaces[namespace]
                else:
                    await self._save_locked(namespace, data)
            except OSError as exc:
                _logger.exception(
                    "lexical index delete failed", extra={"namespace": namespace}
                )
                self._namespaces[namespace] = data
                for chunk in removed:
                    self._insert_locked(data, chunk)
                raise AdapterError(
                    f"failed to persist lexical index for {namespace!r}"
                ) from exc
            except AdapterError:
                # _save_locked already logged and wrapped the OSError;
                # roll back in-memory state so it matches the untouched
                # disk file, then re-raise.
                self._namespaces[namespace] = data
                for chunk in removed:
                    self._insert_locked(data, chunk)
                raise

    async def save(self, path: str, namespace: str = "default") -> None:
        async with self._lock:
            data = self._namespaces.get(namespace)
            if data is None:
                return  # never loaded: write nothing (drift #41)
            await self._save_locked(namespace, data, path)

    async def load(self, path: str, namespace: str = "default") -> None:
        file = self._file_path(path, namespace)
        async with self._lock:
            try:
                content = await asyncio.to_thread(_read_namespace_file, file)
                if content is None:
                    return  # not yet indexed: empty until fed
                payload = json.loads(content)
            except (OSError, json.JSONDecodeError) as exc:
                _logger.exception(
                    "lexical index load failed", extra={"file": str(file)}
                )
                raise AdapterError(f"failed to read lexical index {file}") from exc
            if not isinstance(payload, dict):
                raise VersionMismatchError(
                    f"lexical index {file} is malformed; delete the "
                    "lexical_indices directory and reindex"
                )
            version = payload.get("format_version")
            if version != _FORMAT_VERSION:
                raise VersionMismatchError(
                    f"lexical index {file} has format version {version!r}, "
                    f"expected {_FORMAT_VERSION}; delete the lexical_indices "
                    "directory and reindex"
                )
            records = payload.get("chunks")
            if not isinstance(records, list):
                raise AdapterError(f"lexical index {file} has no chunks list")
            data = _NamespaceData(chunks={}, tf={}, df=Counter(), lengths={})
            for record in records:
                if not isinstance(record, dict):
                    raise AdapterError(
                        f"lexical index {file} has a malformed chunk record"
                    )
                self._insert_locked(data, _chunk_from_dict(record))
            if data.chunks:
                self._namespaces[namespace] = data

    async def list_namespaces(self, path: str) -> list[str]:
        return await asyncio.to_thread(_list_namespace_files, path)

    async def shutdown(self) -> None:
        async with self._lock:
            for namespace in list(self._namespaces):
                await self._save_locked(namespace, self._namespaces[namespace])
