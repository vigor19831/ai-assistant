"""Shared indexing logic — direct adapter calls, no subprocess."""

from __future__ import annotations

import asyncio
import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_assistant.core.logger import get_logger

if TYPE_CHECKING:
    from ai_assistant.core.config import SourceConfig

__all__ = ["index_folder", "read_sources"]

_logger = get_logger("rag.indexing")


def _read_file_sync(path: Path) -> str:
    """Read text file with encoding fallback.  SYNC — call via to_thread."""
    encodings = ["utf-8", "utf-8-sig", "cp1251", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
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
        _logger.warning(
            "Source path does not exist, skipping: %s",
            root,
        )
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
                        "Skipping oversized file %s (%d > %d bytes)",
                        file_path,
                        file_size,
                        max_file_size,
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
            _logger.info(
                "Source '%s': %d documents from %s",
                source.namespace,
                len(docs),
                source.path,
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
    all_errors: list[str] = []

    for namespace, docs in docs_by_ns.items():
        if folder and namespace != folder:
            continue

        if clear:
            try:
                existing = await vector_store.list_by_filter({}, namespace=namespace)
                to_delete = [cid for cid, _meta in existing]
                if to_delete:
                    await vector_store.delete(to_delete, namespace=namespace)
                    _logger.info(
                        "Cleared %d chunks from namespace %s", len(to_delete), namespace
                    )
            except Exception as exc:
                _logger.warning("Failed to clear namespace %s: %s", namespace, exc)
                all_errors.append(f"Clear failed for {namespace}: {exc}")

        try:
            result = await manager.index_documents(docs, namespace=namespace)
            all_results[namespace] = {
                "indexed": result.get("indexed_count", 0),
                "chunks": result.get("chunk_count", 0),
            }
            if result.get("errors"):
                all_errors.extend(result["errors"])

            index_path = vector_store.index_path
            if index_path:
                try:
                    await vector_store.save(index_path, namespace=namespace)
                except Exception as exc:
                    _logger.warning("Auto-save failed for %s: %s", namespace, exc)
                    all_errors.append(f"Auto-save failed for {namespace}: {exc}")

        except Exception as exc:
            _logger.exception("Indexing failed for namespace %s", namespace)
            all_errors.append(f"Indexing failed for {namespace}: {exc}")
            all_results[namespace] = {"indexed": 0, "chunks": 0}

    return {
        "success": not any("failed" in e for e in all_errors),
        "results": all_results,
        "errors": all_errors,
    }
