"""Application lifespan — startup/shutdown with graceful cleanup."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ai_assistant.api.deps import (
    get_chunker_for_config,
    init_adapters,
    shutdown_chunker_if_temporary,
)
from ai_assistant.api.security import get_expected_api_key, set_api_key
from ai_assistant.core.config import AppConfig, SourceConfig, load_config
from ai_assistant.core.constants import (
    ADAPTER_SHUTDOWN_TIMEOUT,
    BACKGROUND_TASKS_SHUTDOWN_TIMEOUT,
    INDEX_IO_TIMEOUT,
)
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.logger import get_logger, setup_logging
from ai_assistant.core.retry import with_retry
from ai_assistant.features.rag.indexing import backfill_lexical_index, index_folder
from ai_assistant.features.rag.manager import SourceWatcher

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

    from ai_assistant.api.deps import InitializedAppState
    from ai_assistant.core.ports.vector_store import IVectorStore

__all__ = ["lifespan"]

logger = get_logger("lifespan")


def _load_config() -> AppConfig:
    """Load config from YAML. Raises FileNotFoundError if file missing."""
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    return load_config(config_path)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle."""
    config = _load_config()
    app.state.config = config

    from ai_assistant.api.static import mount_static

    log_cfg = config.logging
    log_level = log_cfg.level if log_cfg else ("DEBUG" if config.debug else "INFO")
    log_file = log_cfg.file if log_cfg else None
    log_fmt = log_cfg.format if log_cfg else "text"
    max_bytes = log_cfg.max_bytes if log_cfg else 10_485_760
    backup_count = log_cfg.backup_count if log_cfg else 2
    # Enable structured metric logging when JSON format is active and
    # env var AI_METRICS_TO_LOG is set (solo-local debug mode).
    _env_flag = os.getenv("AI_METRICS_TO_LOG", "").lower()
    metrics_to_log = _env_flag in ("1", "true", "yes")
    setup_logging(
        level=log_level,
        log_file=log_file,
        fmt=log_fmt,
        max_bytes=max_bytes,
        backup_count=backup_count,
        metrics_to_log=metrics_to_log,
    )

    mount_static(app, config)

    # Ensure data directories exist before adapters try to write to them.
    data_dirs = [
        Path(config.vector_store.index_path),
        Path(config.storage.db_path).parent,
        Path(config.rag.chat_exports_root),
    ]
    if config.lexical_index is not None:
        data_dirs.append(Path(config.lexical_index.index_path))
    for path in data_dirs:
        await asyncio.to_thread(path.mkdir, parents=True, exist_ok=True)

    if config.security.api_key and get_expected_api_key() is None:
        set_api_key(config.security.api_key)

    if config.security.admin_enabled:
        logger.warning(
            "Admin endpoints enabled. Runtime API key rotation via "
            "/admin/api-key is process-local and will not propagate across "
            "multiple uvicorn/gunicorn workers. Use AI_SECURITY_API_KEY "
            "env var for consistent key distribution in multiprocess mode."
        )

    state = await init_adapters(config)
    app.state.app_state = state

    watcher: SourceWatcher | None = None

    if config.rag.sources:

        async def _index(src: SourceConfig) -> None:
            await _index_source(state, config, src)

        watcher = SourceWatcher(
            sources=config.rag.sources,
            state=state,
            index_fn=_index,
        )

    # Load persisted indices from disk via port contract
    if state.vector_store is not None:
        index_path = state.vector_store.index_path
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            loaded = 0
            skipped = 0
            for ns in namespaces:
                try:
                    await state.vector_store.load(index_path, namespace=ns)
                    loaded += 1
                except (AdapterError, VersionMismatchError) as exc:
                    logger.error(
                        "Index load failed, skipping namespace",
                        extra={"namespace": ns, "error": str(exc), "path": index_path},
                    )
                    skipped += 1
            logger.info(
                "Loaded indices",
                extra={
                    "loaded": loaded,
                    "skipped": skipped,
                    "total": len(namespaces),
                    "path": index_path,
                },
            )
        except (OSError, RuntimeError, AdapterError, VersionMismatchError):
            logger.exception("Index load failed on startup")
            raise

    # Load persisted lexical indices (hybrid 4b). Missing file = no-op
    # (degrades loudly-later, not fatally — drift #73); corrupt or
    # version-mismatched = fatal (drift #73): the message says to
    # delete the folder and reindex — derived data, rebuildable.
    if state.lexical_index is not None:
        lex_path = state.lexical_index.index_path
        try:
            lex_namespaces = await state.lexical_index.list_namespaces(lex_path)
            lex_loaded = 0
            lex_skipped = 0
            for ns in lex_namespaces:
                try:
                    await state.lexical_index.load(lex_path, namespace=ns)
                    lex_loaded += 1
                except (AdapterError, VersionMismatchError) as exc:
                    logger.error(
                        "Lexical index load failed, skipping namespace",
                        extra={"namespace": ns, "error": str(exc)},
                    )
                    lex_skipped += 1
            logger.info(
                "Loaded lexical indices",
                extra={
                    "loaded": lex_loaded,
                    "skipped": lex_skipped,
                    "total": len(lex_namespaces),
                    "path": lex_path,
                },
            )
        except (OSError, RuntimeError, AdapterError, VersionMismatchError):
            logger.exception("Lexical index load failed on startup")
            raise

    # Fill lexical mirror holes from the vector inventory (drift #146)
    # before the watcher starts — no reindex pass can race it.
    await _backfill_lexical_mirror(state)

    if watcher is not None:
        watcher.start()

    try:
        yield
    finally:
        if watcher is not None:
            await watcher.stop()
        await _async_cleanup(app, config)


async def _index_source(
    state: InitializedAppState, config: AppConfig, src: SourceConfig
) -> None:
    """Index one watcher source; ERROR-log any run that reports failure.

    The watcher consumes the snapshot on any non-raising return, so a
    failed run (pre-flight refusal, chunking error, empty source) must
    at least be loud. No retry here: deterministic refusals must not be
    retried, and transient failures are already retried inside the
    adapters (drift #43 — exactly one retry layer).
    """
    ns_cfg = config.namespaces.get(src.namespace)
    chunker = get_chunker_for_config(state, ns_cfg.chunk_size if ns_cfg else None)
    try:
        result = await index_folder(
            target_namespace=None,
            clear=False,
            chunker=chunker,
            embedder=state.embedder,
            vector_store=state.vector_store,
            max_file_size=config.vector_store.max_document_size,
            sources=[src],
            index_path=state.vector_store.index_path,
            lexical_index=state.lexical_index,
            encodings=list(config.rag.file_encodings),
        )
        if not result.get("success", False):
            logger.error(
                "Watcher reindex failed",
                extra={
                    "namespace": src.namespace,
                    "errors": result.get("errors", []),
                },
            )
    finally:
        await shutdown_chunker_if_temporary(chunker, state.chunker)


async def _backfill_lexical_mirror(state: InitializedAppState) -> None:
    """Fill lexical mirror holes from the vector inventory (drift #146).

    Copies stored texts — the embedder is never involved. Module-level
    for direct testing (same precedent as _index_source, drift #113).
    A failure degrades to the old behavior (the watcher re-indexes the
    holes through the embedder) and stays loud: startup never dies here.
    """
    if state.lexical_index is None or state.vector_store is None:
        return
    try:
        copied = await backfill_lexical_index(
            state.vector_store, state.lexical_index
        )
        if copied:
            logger.info(
                "Lexical mirror backfilled",
                extra={
                    "namespaces": len(copied),
                    "chunks": sum(copied.values()),
                },
            )
    except Exception:
        logger.exception("Lexical mirror backfill failed")


async def _async_cleanup(app: FastAPI, config: AppConfig) -> None:
    """Async cleanup actions."""
    try:
        state = app.state.app_state
    except AttributeError:
        logger.warning("No app state found during shutdown")
        return

    # 1. Persist indices FIRST.
    #
    # WHY: Background tasks may hang (reindex timeout is 4h). If we wait for
    # tasks before persisting, a hung task prevents index save entirely.
    # Slightly stale indices are acceptable; losing all indices is not.
    # See architecture.md
    try:
        index_path = state.vector_store.index_path
        namespaces = await state.vector_store.list_namespaces(index_path)
        saved = 0
        for ns in namespaces:
            try:
                await _save_index_with_retry(state.vector_store, index_path, ns)
                logger.info("Index saved", extra={"path": index_path, "namespace": ns})
                saved += 1
            except Exception:
                logger.exception(
                    "Index save failed after retries",
                    extra={"path": index_path, "namespace": ns},
                )
        logger.info(
            "Indices persisted",
            extra={"saved": saved, "total": len(namespaces)},
        )
    except Exception:
        logger.exception("Index save failed")

    # 1b. Persist lexical indices (hybrid 4b) — same section-1 rule:
    # before the background-tasks wait, so a hung task cannot block
    # the save. No retry wrapper: the adapter's shutdown() saves again
    # (idempotent), and stacked retry is banned (drift #43).
    if state.lexical_index is not None:
        try:
            lex_path = state.lexical_index.index_path
            for ns in await state.lexical_index.list_namespaces(lex_path):
                try:
                    await asyncio.wait_for(
                        state.lexical_index.save(lex_path, namespace=ns),
                        timeout=INDEX_IO_TIMEOUT,
                    )
                except Exception:
                    logger.exception(
                        "Lexical index save failed",
                        extra={"namespace": ns},
                    )
        except Exception:
            logger.exception("Lexical index save failed")

    # 2. Wait for background tasks before adapter shutdown
    try:
        await state.task_registry.shutdown(wait_for=BACKGROUND_TASKS_SHUTDOWN_TIMEOUT)
        logger.info("Background tasks shutdown complete")
    except Exception:
        logger.exception("Background tasks shutdown failed")

    # 3. Graceful adapter shutdown — add new closable adapters here
    adapters = (
        (state.lexical_index, "lexical_index"),
        (state.llm, "llm"),
        (state.embedder, "embedder"),
        (state.vector_store, "vector_store"),
        (state.storage, "storage"),
        (state.reranker, "reranker"),
        (state.chunker, "chunker"),
        (state.tokenizer, "tokenizer"),
    )

    for adapter, name in adapters:
        if adapter is None:
            continue
        try:
            await asyncio.wait_for(adapter.shutdown(), timeout=ADAPTER_SHUTDOWN_TIMEOUT)
            logger.info("Adapter shutdown complete", extra={"adapter": name})
        except TimeoutError:
            logger.warning("Adapter shutdown timed out", extra={"adapter": name})
        except Exception:
            logger.exception("Adapter shutdown failed", extra={"adapter": name})

    # Adapters own their HTTP clients; each closes its own in shutdown()


@with_retry(max_retries=3, delay=0.5, backoff=2.0)
async def _save_index_with_retry(
    vector_store: IVectorStore, index_path: str, namespace: str
) -> None:
    """Save index with retry (10 s per attempt).

    Raises:
        AdapterError: If a single attempt times out.
        Exception: If save fails after all retries.
    """
    try:
        await asyncio.wait_for(
            vector_store.save(index_path, namespace=namespace),
            timeout=INDEX_IO_TIMEOUT,
        )
    except TimeoutError:
        raise AdapterError("Index save timed out, will retry") from None
