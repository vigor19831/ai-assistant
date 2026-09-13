"""Shared indexing logic — direct adapter calls, no subprocess."""
from __future__ import annotations

import asyncio
import fnmatch
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.documents import Document
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import increment_counter

if TYPE_CHECKING:
    from ai_assistant.core.config import SourceConfig
    from ai_assistant.core.ports.chunker import IChunker
    from ai_assistant.core.ports.embedder import IEmbedder
    from ai_assistant.core.ports.vector_store import IVectorStore

__all__ = ["index_folder", "read_sources"]

_logger = get_logger("rag.indexing")


def _read_file_sync(path: Path) -> str | None:
    """Read text file with encoding fallback.  SYNC — call via to_thread.

    Returns None when the OS refuses the read (locked file, permissions).
    An empty string means the file was read and is genuinely empty.
    """
    # utf-8-sig first: decodes plain UTF-8 identically and strips the BOM.
    # Plain utf-8 must not precede it — it accepts BOM files "successfully",
    # leaking U+FEFF into chunk text (drift #46).
    encodings = ["utf-8-sig", "cp1251", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except OSError:
            # OS refused open/read: unreadable is not empty.
            return None
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
    skip: dict[str, tuple[str | None, int, int]] | None = None,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Collect documents from a single source configuration.

    Returns (docs, uris): docs to index plus every uri present on disk
    (matched, size-ok, non-empty — including skipped-unchanged ones).
    An unreadable file (locked, permissions) yields no doc but KEEPS
    its uri in *uris* so orphan cleanup does not treat it as deleted.
    A file in *skip* with the same mtime and a complete stored chunk
    set is NOT read (drift #93 conditions, checked before the read).
    """
    docs: list[dict[str, Any]] = []
    uris: set[str] = set()
    skipped_files = 0
    root = Path(source.path).expanduser().resolve()
    if not root.exists():
        _logger.warning(f"Source path does not exist, skipping: {root}")
        return docs, uris

    # Sorted for deterministic doc order: checkpoint sequence and test
    # assertions must not depend on filesystem iteration order.
    iterator = sorted(root.rglob("*")) if source.recursive else sorted(root.iterdir())
    for file_path in iterator:
        if not file_path.is_file():
            continue
        if not _match_patterns(file_path, source.include):
            continue
        # Guard: skip files exceeding max size before reading into memory
        try:
            st = file_path.stat()
        except OSError:
            # Unreadable is not deleted — preserve the stored chunks.
            _logger.warning(f"Cannot stat {file_path}, keeping its chunks")
            uris.add(file_path.relative_to(root).as_posix())
            continue
        if max_file_size is not None and st.st_size > max_file_size:
            _logger.warning(
                f"Skipping oversized file {file_path} "
                f"({st.st_size} > {max_file_size} bytes)"
            )
            continue
        source_uri = file_path.relative_to(root).as_posix()
        last_modified = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        if skip is not None:
            entry = skip.get(source_uri)
            # Same contract as _filter_unchanged_docs, checked before
            # the read: mtime equal AND stored chunk count == declared
            # total. Partial stores / missing total_chunks fail open
            # (-1 never equals a real count) — re-read, idempotent
            # (drift #93).
            if (
                entry is not None
                and entry[0] is not None
                and entry[0] == last_modified
                and entry[1] == entry[2]
            ):
                skipped_files += 1
                uris.add(source_uri)
                continue
        content = _read_file_sync(file_path)
        if content is None:
            # Unreadable is not deleted: keep the uri so orphan cleanup
            # preserves the stored chunks (locked file, permissions).
            _logger.warning(f"Cannot read {file_path}, keeping its chunks")
            uris.add(source_uri)
            continue
        if not content.strip():
            continue
        uris.add(source_uri)
        docs.append(
            {
                "id": file_path.stem,
                "content": content,
                "metadata": {
                    "source": source_uri,
                    "folder": source.namespace,
                    "source_uri": source_uri,
                    "type": "document",
                    "last_modified": last_modified,
                    "original_path": str(file_path),
                },
            }
        )
    if skipped_files:
        _logger.info(
            f"Source {source.namespace}: {skipped_files} unchanged file(s) "
            "not re-read"
        )
    return docs, uris


def _uri_stats(
    all_meta: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, str | None], dict[str, int], dict[str, int]]:
    """Per-uri (mtime, stored chunk count, declared total) from chunk metadata.

    Shared by the pre-read skip (index_folder) and the post-read filter
    (_filter_unchanged_docs) — one definition of "unchanged + complete".
    """
    mtime: dict[str, str | None] = {}
    count: dict[str, int] = {}
    total: dict[str, int] = {}
    for _cid, meta in all_meta:
        uri = meta.get("source_uri")
        if not uri:
            continue
        mtime[uri] = meta.get("last_modified")
        count[uri] = count.get(uri, 0) + 1
        # total_chunks lives on CHUNK metadata (set by the chunker for
        # the whole batch; document metadata from read_sources has no
        # such field). Every chunk of one uri carries the same value.
        tc = meta.get("total_chunks")
        if isinstance(tc, int):
            total[uri] = tc
    return mtime, count, total


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
    return _read_sources_incremental(sources, max_file_size)[0]


def _read_sources_incremental(
    sources: list[SourceConfig],
    max_file_size: int | None = None,
    skip_by_ns: dict[str, dict[str, tuple[str | None, int, int]]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, set[str]]]:
    """Read sources; unchanged+complete files (per *skip_by_ns*) are
    not read from disk.

    Returns ({namespace: [docs]}, {namespace: {uris on disk}}).
    """
    result: dict[str, list[dict[str, Any]]] = {}
    inventories: dict[str, set[str]] = {}
    for source in sources:
        skip = skip_by_ns.get(source.namespace) if skip_by_ns else None
        docs, uris = _collect_files_sync(
            source, max_file_size=max_file_size, skip=skip
        )
        if uris:
            inventories[source.namespace] = (
                inventories.get(source.namespace, set()) | uris
            )
        if docs:
            existing = result.get(source.namespace, [])
            result[source.namespace] = existing + docs
            n_docs = len(docs)
            _logger.info(
                f"Source {source.namespace}: {n_docs} docs from {source.path}"
            )
    return result, inventories


async def _clear_namespace_chunks(
    vector_store: IVectorStore, namespace: str
) -> str | None:
    """Delete all chunks in namespace. Returns error message or None."""
    try:
        existing = await vector_store.list_by_filter({}, namespace=namespace)
        to_delete = [cid for cid, _meta in existing]
        if to_delete:
            await vector_store.delete(to_delete, namespace=namespace)
            _logger.info(f"Cleared {len(to_delete)} chunks from {namespace}")
        return None
    except Exception as exc:
        _logger.warning(f"Failed to clear namespace {namespace}: {exc}")
        return f"Clear failed for {namespace}: {exc}"


async def _cleanup_orphan_chunks(
    vector_store: IVectorStore,
    namespace: str,
    current_uris: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    """Remove chunks whose source_uri no longer exists on disk.

    Safe because original documents are the source of truth; indices
    are derived. Returns existing chunk metadata for freshness checks.
    """
    all_meta: list[tuple[str, dict[str, Any]]] = []
    try:
        all_meta = await vector_store.list_by_filter({}, namespace=namespace)
        # A no-files disk with stored chunks means the source directory is
        # temporarily unavailable (sleep, network, unmount) — cleanup is
        # skipped to prevent data loss.
        if not current_uris and all_meta:
            _logger.warning(
                f"Skipping orphan cleanup for {namespace}: "
                f"0 docs from source but {len(all_meta)} chunks exist",
                extra={"namespace": namespace, "existing_chunks": len(all_meta)},
            )
            return all_meta
        orphan_ids = [
            cid
            for cid, meta in all_meta
            if meta.get("source_uri")
            and meta.get("source_uri") not in current_uris
        ]
        if orphan_ids:
            await vector_store.delete(orphan_ids, namespace=namespace)
            increment_counter(
                "ai_assistant_rag_orphans_removed_total",
                labels={"namespace": namespace},
                value=len(orphan_ids),
            )
            _logger.info(f"Removed {len(orphan_ids)} orphan chunks from {namespace}")
    except Exception as exc:
        _logger.warning(f"Orphan cleanup failed for {namespace}: {exc}")
    return all_meta


def _filter_unchanged_docs(
    docs: list[dict[str, Any]],
    all_meta: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Skip docs whose source_uri is already indexed with the same
    mtime and a complete chunk set.

    Changed files pass through (upsert replaces old chunks). Duplicates
    within the current batch are also skipped.
    """
    existing_uri_mtime, existing_uri_count, existing_uri_total = _uri_stats(all_meta)

    seen_uris: set[str] = set()
    new_docs: list[dict[str, Any]] = []
    for d in docs:
        uri = d.get("metadata", {}).get("source_uri")
        if uri is None:
            new_docs.append(d)
            continue
        if uri in seen_uris:
            continue
        if uri in existing_uri_mtime:
            old_mtime = existing_uri_mtime[uri]
            new_mtime = d.get("metadata", {}).get("last_modified")
            # Only skip when both mtimes are known and equal AND the
            # store holds as many chunks for the uri as the stored
            # chunks themselves declare (total_chunks, chunk-level).
            # A partial store (external clear, interrupted write — drift
            # #82, reproduced live 2026-09-10: half-cut chunks, mtime
            # untouched, watcher skipped all) must re-index; the upsert
            # then restores the full set. Chunks without total_chunks
            # fail open (-1 never equals a real count) — re-index,
            # idempotent, never permanently skipped.
            complete = existing_uri_count.get(uri, 0) == existing_uri_total.get(
                uri, -1
            )
            if (
                old_mtime is not None
                and old_mtime == new_mtime
                and complete
            ):
                # Unchanged on disk and fully stored, skip
                continue
        seen_uris.add(uri)
        new_docs.append(d)
    return new_docs


async def _preflight_max_chunks(
    namespace: str,
    new_docs: list[dict[str, Any]],
    stored: dict[str, tuple[str | None, int, int]],
    inventory: set[str],
    chunker: IChunker,
    max_chunks: int,
) -> str | None:
    """Predict a max_chunks overflow BEFORE embedding starts (stage 1).

    Chunks every new document (cheap CPU) and replays the per-document
    upsert sequence against the limit, mirroring the atomic upsert
    contract (#88): the namespace size AFTER replacement, not the
    transient peak. The store stays the final guard (#48) — this check
    only refuses the run up front, in a human-readable form, instead
    of an AdapterError hours into a long indexing pass.

    Returns the refusal message, or None when the pass fits. A
    chunking error skips the check: the run then fails on that
    document exactly as it does today — the pre-flight must not add
    new failure modes.
    """
    try:
        counts: list[int] = []
        for doc in new_docs:
            doc_id = doc.get("id")
            if not doc_id:
                counts.append(0)
                continue
            chunks = await chunker.chunk(
                Document(
                    id=doc_id,
                    content=doc.get("content", ""),
                    metadata=doc.get("metadata", {}),
                )
            )
            counts.append(len(chunks))
    except Exception:
        _logger.warning(
            "Pre-flight chunk counting failed, skipping the check",
            extra={"namespace": namespace},
        )
        return None

    existing = sum(entry[1] for uri, entry in stored.items() if uri in inventory)
    total = existing
    for doc, new_count in zip(new_docs, counts, strict=True):
        uri = doc.get("metadata", {}).get("source_uri")
        old_count = stored.get(uri, (None, 0, -1))[1]
        projected = total - old_count + new_count
        if projected > max_chunks:
            return (
                "Pre-flight max_chunks check failed for namespace "
                f"'{namespace}': document '{doc.get('id', 'unknown')}' would "
                f"push the namespace to {projected} chunks "
                f"(existing {existing}, max_chunks {max_chunks}). "
                "No embedding started. Split the source into more "
                "namespaces or raise vector_store.max_chunks."
            )
        total = projected
    return None


async def index_folder(
    target_namespace: str | None,
    clear: bool,
    chunker: IChunker,
    embedder: IEmbedder,
    vector_store: IVectorStore,
    max_file_size: int | None = None,
    sources: list[SourceConfig] | None = None,
    index_path: str | None = None,
) -> dict[str, Any]:
    """Index documents from disk folders directly into vector store.

    Args:
        target_namespace: Specific namespace to index, or None for all.
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

    manager = IndexingManager(
        chunker=chunker,
        embedder=embedder,
        vector_store=vector_store,
    )

    all_results: dict[str, Any] = {}
    all_indexed_uris: dict[str, dict[str, list[str]]] = {}
    all_errors: list[str] = []
    processed_any = False

    expected_namespaces = {src.namespace for src in sources}
    if target_namespace:
        expected_namespaces = {
            ns for ns in expected_namespaces if ns == target_namespace
        }

    # Phase 1 — fetch stored uri stats BEFORE reading disk: unchanged +
    # complete files then skip the read itself (#93 contract, moved
    # before the disk read). clear wipes the store inside this loop,
    # so after a clear nothing is skipped.
    skip_by_ns: dict[str, dict[str, tuple[str | None, int, int]]] = {}
    for namespace in sorted(expected_namespaces):
        if clear:
            clear_error = await _clear_namespace_chunks(vector_store, namespace)
            if clear_error:
                all_errors.append(clear_error)
        stored_meta = await vector_store.list_by_filter({}, namespace=namespace)
        stored_mtime, stored_count, stored_total = _uri_stats(stored_meta)
        skip_by_ns[namespace] = {
            uri: (
                stored_mtime.get(uri),
                stored_count.get(uri, 0),
                stored_total.get(uri, -1),
            )
            for uri in stored_mtime
        }

    # Phase 2 — read only what the store does not vouch for.
    docs_by_ns, inventory_by_ns = await asyncio.to_thread(
        _read_sources_incremental,
        sources,
        max_file_size,
        skip_by_ns,
    )
    if not inventory_by_ns:
        # An empty corpus is a failed run, not a silent success: a typo
        # in source.path or a fully emptied tree must be visible (#113).
        return {"success": False, "results": {}, "errors": ["No documents found"]}

    # Sorted for cross-process determinism (#114): raw set iteration
    # order varies with string-hash randomization.
    for namespace in sorted(expected_namespaces):
        docs = docs_by_ns.get(namespace, [])
        processed_any = True

        all_meta = await _cleanup_orphan_chunks(
            vector_store, namespace, inventory_by_ns.get(namespace, set())
        )
        new_docs = _filter_unchanged_docs(docs, all_meta)

        skipped = len(docs) - len(new_docs)
        if skipped:
            _logger.info(
                f"Skipped {skipped} documents "
                f"(source_uri already in index) for namespace {namespace}"
            )

        if not new_docs:
            all_results[namespace] = {"indexed": 0, "chunks": 0}
            continue

        # Pre-flight max_chunks check (scale stage 1): refuse before the
        # embedding loop starts — a human-readable error instead of an
        # AdapterError mid-run. The store still enforces the limit (#48).
        refusal = await _preflight_max_chunks(
            namespace,
            new_docs,
            skip_by_ns.get(namespace, {}),
            inventory_by_ns.get(namespace, set()),
            chunker,
            vector_store.config.max_chunks,
        )
        if refusal is not None:
            _logger.error(refusal, extra={"namespace": namespace})
            all_errors.append(refusal)
            all_results[namespace] = {"indexed": 0, "chunks": 0}
            continue

        # Incremental indexing (drift #64): each document is a
        # transaction — embed, upsert, checkpoint to disk. A timeout,
        # crash or restart loses at most the current document; the
        # next pass skips already-indexed docs (filter_unchanged_docs)
        # and continues from the last checkpoint. The watcher window
        # becomes a pause between checkpoints, never a full reset.
        total_docs = len(new_docs)
        indexed_count = 0
        chunk_count = 0
        ns_uris: dict[str, list[str]] = {}
        try:
            for doc_pos, doc in enumerate(new_docs, start=1):
                result = await manager.index_documents([doc], namespace=namespace)
                indexed_count += result.get("indexed_count", 0)
                chunk_count += result.get("chunk_count", 0)
                doc_uris = result.get("indexed_uris", {})
                for uri, chunk_ids in doc_uris.items():
                    ns_uris[uri] = chunk_ids
                if result.get("errors"):
                    all_errors.extend(result["errors"])
                if index_path:
                    try:
                        await vector_store.save(index_path, namespace=namespace)
                    except Exception as exc:
                        _logger.warning(
                            f"Checkpoint save failed for {namespace}: {exc}"
                        )
                        all_errors.append(
                            f"Checkpoint save failed for {namespace}: {exc}"
                        )
                _logger.info(
                    f"index.progress {namespace} {doc_pos}/{total_docs} "
                    f"({round(100 * doc_pos / total_docs)}%) "
                    f"chunks={chunk_count}"
                )
        except Exception as exc:
            _logger.exception(f"Indexing failed for namespace {namespace}")
            all_errors.append(f"Indexing failed for {namespace}: {exc}")

        if ns_uris:
            all_indexed_uris[namespace] = ns_uris
        all_results[namespace] = {
            "indexed": indexed_count,
            "chunks": chunk_count,
        }

    if target_namespace and not processed_any:
        all_errors.append(
            f"Namespace '{target_namespace}' not found in configured sources"
        )
        return {
            "success": False,
            "results": all_results,
            "errors": all_errors,
        }

    # Success means exactly "no errors" (#113) — the old substring
    # check ("failed" in error) let "Failed to chunk document ..."
    # (capital F) pass as a success.
    return {
        "success": not all_errors,
        "results": all_results,
        "indexed_uris": all_indexed_uris,
        "errors": all_errors,
    }
