"""Shared indexing logic — direct adapter calls, no subprocess."""

from __future__ import annotations

import asyncio
import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_assistant.core.logger import get_logger

if TYPE_CHECKING:
    from ai_assistant.core.config import SourceConfig
    from ai_assistant.core.ports.vector_store import IVectorStore

__all__ = ["cleanup_stale", "index_folder", "read_sources"]

_logger = get_logger("rag.indexing")


def _read_file_sync(path: Path) -> str:
    """Read text file with encoding fallback.  SYNC — call via to_thread."""
    encodings = ["utf-8", "utf-8-sig", "cp1251", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError, OSError):
            continue
    return ""


def _match_patterns(file_path: Path, patterns: list[str]) -> bool:
    """Return True if file name matches any of the glob patterns."""
    name = file_path.name
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _collect_files_sync(
    source: SourceConfig,
    max_file_size: int | None = None,
) -> list[dict[str, Any]]:
    """Collect documents from a single source configuration.

    Returns list of document dicts for this source's namespace.
    """
    docs: list[dict[str, Any]] = []
    root = Path(source.path).expanduser().resolve()

    if not root.exists():
        _logger.warning(f"Source path does not exist, skipping: {root}")
        return docs

    iterator = root.rglob("*") if source.recursive else root.iterdir()

    for file_path in iterator:
        if not file_path.is_file():
            continue
        if not _match_patterns(file_path, source.include):
            continue

        # Guard: skip files exceeding max size before reading into memory
        if max_file_size is not None:
            try:
                file_size = file_path.stat().st_size
                if file_size > max_file_size:
                    _logger.warning(
                        f"Skipping oversized file {file_path} "
                        f"({file_size} > {max_file_size} bytes)"
                    )
                    continue
            except OSError:
                continue

        content = _read_file_sync(file_path)
        if not content.strip():
            continue

        source_uri = file_path.relative_to(root).as_posix()

        docs.append(
            {
                "id": file_path.stem,
                "content": content,
                "metadata": {
                    "source": source_uri,
                    "folder": source.namespace,
                    "source_uri": source_uri,
                    "type": "document",
                },
            }
        )

    return docs


def read_sources(
    sources: list[SourceConfig],
    max_file_size: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Read all configured sources and group by namespace.

    Args:
        sources: List of SourceConfig from RAGConfig.
        max_file_size: Skip files larger than this (bytes).

    Returns:
        {namespace: [document_dicts]}.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        docs = _collect_files_sync(source, max_file_size=max_file_size)
        if docs:
            existing = result.get(source.namespace, [])
            result[source.namespace] = existing + docs
            n_docs = len(docs)
            _logger.info(
                f"Source {source.namespace}: {n_docs} docs from {source.path}"
            )
    return result


async def index_folder(
    folder: str | None,
    clear: bool,
    chunker: Any,
    embedder: Any,
    vector_store: Any,
    max_file_size: int | None = None,
    sources: list[SourceConfig] | None = None,
    index_path: str | None = None,
) -> dict[str, Any]:
    """Index documents from disk folders directly into vector store.

    Args:
        folder: Specific folder to index, or None for all.
        clear: If True, clear existing chunks in each namespace before indexing.
        chunker: IChunker instance.
        embedder: IEmbedder instance.
        vector_store: IVectorStore instance.
        max_file_size: Max file size in bytes before skipping (guard).
        sources: List of SourceConfig — specifies document sources.

    Returns:
        Dict with results per namespace and any errors.
    """
    from ai_assistant.features.rag.manager import IndexingManager

    if not sources:
        _logger.warning("No sources configured, nothing to index")
        return {"success": False, "results": {}, "errors": ["No sources configured"]}

    docs_by_ns = await asyncio.to_thread(
        read_sources,
        sources,
        max_file_size=max_file_size,
    )
    if not docs_by_ns:
        return {"success": True, "results": {}, "errors": ["No documents found"]}

    manager = IndexingManager(
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
    )

    all_results: dict[str, Any] = {}
    all_indexed_uris: dict[str, dict[str, list[str]]] = {}
    all_errors: list[str] = []
    processed_any = False

    for namespace, docs in docs_by_ns.items():
        if folder and namespace != folder:
            continue
        processed_any = True

        if clear:
            try:
                existing = await vector_store.list_by_filter({}, namespace=namespace)
                to_delete = [cid for cid, _meta in existing]
                if to_delete:
                    await vector_store.delete(to_delete, namespace=namespace)
                    n_cleared = len(to_delete)
                    _logger.info(f"Cleared {n_cleared} chunks from {namespace}")
            except Exception as exc:
                _logger.warning(f"Failed to clear namespace {namespace}: {exc}")
                all_errors.append(f"Clear failed for {namespace}: {exc}")

        # Deduplicate: skip documents whose source_uri already exists in index.
        # This makes re-indexing idempotent without changing disk format.
        existing_uris: set[str] = set()
        try:
            all_meta = await vector_store.list_by_filter({}, namespace=namespace)
            for _cid, meta in all_meta:
                uri = meta.get("source_uri")
                if uri:
                    existing_uris.add(uri)
        except Exception as exc:
            _logger.warning(f"Could not list existing chunks for dedup: {exc}")

        # Deduplicate: skip documents whose source_uri already exists in index
        # OR was already seen earlier in this batch (prevents duplicates from
        # multiple SourceConfig entries pointing to the same file).
        seen_uris: set[str] = set()
        new_docs: list[dict[str, Any]] = []
        for d in docs:
            uri = d.get("metadata", {}).get("source_uri")
            if uri is None:
                new_docs.append(d)
                continue
            if uri in existing_uris or uri in seen_uris:
                continue
            seen_uris.add(uri)
            new_docs.append(d)
        skipped = len(docs) - len(new_docs)
        if skipped:
            _logger.info(
                f"Skipped {skipped} documents "
                f"(source_uri already in index) for namespace {namespace}"
            )

        if not new_docs:
            all_results[namespace] = {"indexed": 0, "chunks": 0}
            continue

        try:
            result = await manager.index_documents(new_docs, namespace=namespace)
            all_results[namespace] = {
                "indexed": result.get("indexed_count", 0),
                "chunks": result.get("chunk_count", 0),
            }
            ns_uris = result.get("indexed_uris", {})
            if ns_uris:
                all_indexed_uris[namespace] = ns_uris
            if result.get("errors"):
                all_errors.extend(result["errors"])

            if index_path:
                try:
                    await vector_store.save(index_path, namespace=namespace)
                except Exception as exc:
                    _logger.warning(f"Auto-save failed for {namespace}: {exc}")
                    all_errors.append(f"Auto-save failed for {namespace}: {exc}")

        except Exception as exc:
            _logger.exception(f"Indexing failed for namespace {namespace}")
            all_errors.append(f"Indexing failed for {namespace}: {exc}")
            all_results[namespace] = {"indexed": 0, "chunks": 0}

    if folder and not processed_any:
        all_errors.append(f"Folder '{folder}' not found in configured sources")
        return {
            "success": False,
            "results": all_results,
            "errors": all_errors,
        }

    return {
        "success": not any("failed" in e for e in all_errors),
        "results": all_results,
        "indexed_uris": all_indexed_uris,
        "errors": all_errors,
    }


async def cleanup_stale(
    vector_store: IVectorStore,
    indexed_uris: dict[str, dict[str, list[str]]],
) -> dict[str, Any]:
    """Remove chunks whose source_uri is not present in indexed_uris.

    Args:
        vector_store: IVectorStore instance.
        indexed_uris: {namespace: {source_uri: [chunk_ids]}} — mapping
            of source_uris that were just indexed.

    Returns:
        {"removed": int, "errors": [str]}.
    """
    total_removed = 0
    errors: list[str] = []

    for namespace, valid_uris in indexed_uris.items():
        try:
            all_chunks = await vector_store.list_by_filter({}, namespace=namespace)
            to_delete: list[str] = []
            for chunk_id, meta in all_chunks:
                uri = meta.get("source_uri")
                if uri is not None and uri not in valid_uris:
                    to_delete.append(chunk_id)

            if to_delete:
                await vector_store.delete(to_delete, namespace=namespace)
                total_removed += len(to_delete)
                _logger.info(
                    f"Removed {len(to_delete)} stale chunks from {namespace}"
                )
        except Exception as exc:
            _logger.exception(f"Cleanup stale failed for {namespace}")
            errors.append(f"Cleanup stale failed for {namespace}: {exc}")

    return {"removed": total_removed, "errors": errors}
