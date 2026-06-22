"""Shared indexing logic — direct adapter calls, no subprocess."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_assistant.core.logger import get_logger

__all__ = ["index_folder"]

_logger = get_logger("rag.indexing")

DOCUMENTS_ROOT = Path("sources")
SUPPORTED_EXTENSIONS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".log"}
CHUNK_SIZE = 100_000  # Max chars per document chunk


def _read_file(path: Path) -> str:
    """Read text file with encoding fallback."""
    encodings = ["utf-8", "utf-8-sig", "cp1251", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


def _discover_documents(
    folder: str | None = None,
    max_file_size: int | None = None,
    documents_root: Path | None = None,
    exclude_roots: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Discover documents in folders. Returns {namespace: [docs]}."""
    result: dict[str, list[dict[str, Any]]] = {}
    root = Path(documents_root) if documents_root is not None else DOCUMENTS_ROOT
    exclude_set = set(exclude_roots or [])

    if folder:
        folders = [root / folder]
    else:
        if not root.exists():
            return {}
        folders = [d for d in root.iterdir() if d.is_dir()]

    for folder_path in folders:
        if folder_path.name in exclude_set:
            _logger.info("Skipping excluded folder: %s", folder_path)
            continue
        namespace = folder_path.name
        docs: list[dict[str, Any]] = []

        for file_path in folder_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
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

            content = _read_file(file_path)
            if not content.strip():
                continue

            rel_source = str(file_path.relative_to(root))
            # Relative path from documents_root — no absolute path leakage
            source_uri = file_path.relative_to(root).as_posix()

            if len(content) > CHUNK_SIZE:
                for i, start in enumerate(range(0, len(content), CHUNK_SIZE)):
                    chunk = content[start : start + CHUNK_SIZE]
                    docs.append(
                        {
                            "id": f"{file_path.stem}_chunk{i}",
                            "content": chunk,
                            "metadata": {
                                "source": rel_source,
                                "folder": namespace,
                                "chunk": i,
                                "source_uri": source_uri,  # Pass through to chunker
                            },
                        }
                    )
            else:
                docs.append(
                    {
                        "id": file_path.stem,
                        "content": content,
                        "metadata": {
                            "source": rel_source,
                            "folder": namespace,
                            "source_uri": source_uri,  # Pass through to chunker
                        },
                    }
                )

        if docs:
            result[namespace] = docs

    return result


async def index_folder(
    folder: str | None,
    clear: bool,
    chunker: Any,
    embedder: Any,
    vector_store: Any,
    max_file_size: int | None = None,
    documents_root: Path | None = None,
    exclude_roots: list[str] | None = None,
) -> dict[str, Any]:
    """Index documents from disk folders directly into vector store.

    Args:
        folder: Specific folder to index, or None for all.
        clear: If True, clear existing chunks in each namespace before indexing.
        chunker: IChunker instance.
        embedder: IEmbedder instance.
        vector_store: IVectorStore instance.
        max_file_size: Max file size in bytes before skipping (guard).
        documents_root: Root path for document folders. Falls back to DOCUMENTS_ROOT.

    Returns:
        Dict with results per namespace and any errors.
    """
    from ai_assistant.features.rag.manager import IndexingManager

    docs_by_ns = _discover_documents(
        folder,
        max_file_size=max_file_size,
        documents_root=documents_root,
        exclude_roots=exclude_roots,
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

            index_path = getattr(vector_store.config, "index_path", None)
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
