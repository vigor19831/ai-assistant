"""Application lifespan — startup/shutdown with graceful cleanup."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from ai_assistant.api.deps import init_adapters
from ai_assistant.api.security import get_expected_api_key, set_api_key
from ai_assistant.core.config import AppConfig, load_config
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.logger import get_logger, setup_logging
from ai_assistant.core.retry import with_retry

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

__all__ = ["lifespan"]

logger = get_logger("lifespan")


def _load_config() -> AppConfig:
    """Load config from YAML, fallback to env defaults."""
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

    try:
        yield
    finally:
        await _async_cleanup(app, config)


async def _async_cleanup(app: FastAPI, config: AppConfig) -> None:
    """Async cleanup actions.

    Sets app.state.shutdown_degraded = True if index persistence fails
    so that the lifespan caller can react (e.g., non-zero exit).
    """
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
    # See architectural_strategy.md §5.1 — shutdown order is intentional.
    try:
        index_path = state.vector_store.index_path
        namespaces = await state.vector_store.list_namespaces(index_path)
        saved = 0
        for ns in namespaces:
            try:
                await _save_index_with_retry(
                    state.vector_store, index_path, ns
                )
                logger.info(
                    "Index saved", extra={"path": index_path, "namespace": ns}
                )
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
        app.state.shutdown_degraded = True

    # 2. Wait for background tasks before adapter shutdown
    try:
        await state.task_registry.shutdown(wait_for=30.0)
        logger.info("Background tasks shutdown complete")
    except Exception:
        logger.exception("Background tasks shutdown failed")

    # 3. Graceful adapter shutdown — add new closable adapters here
    adapters = (
        (state.llm, "llm"),
        (state.embedder, "embedder"),
        (state.vector_store, "vector_store"),
        (state.storage, "storage"),
        (state.reranker, "reranker"),
        (state.chunker, "chunker"),
        (state.tokenizer, "tokenizer"),
    )

    for adapter, name in adapters:
        try:
            await asyncio.wait_for(adapter.shutdown(), timeout=5.0)
            logger.info("Adapter shutdown complete", extra={"adapter": name})
        except TimeoutError:
            logger.warning("Adapter shutdown timed out", extra={"adapter": name})
        except Exception:
            logger.exception("Adapter shutdown failed", extra={"adapter": name})

    # Adapters own their HTTP clients; each closes its own in shutdown()


@with_retry(max_retries=3, delay=0.5, backoff=2.0)
async def _save_index_with_retry(
    vector_store: Any, index_path: str, namespace: str
) -> None:
    """Save index with retry (10 s per attempt).

    Raises:
        AdapterError: If a single attempt times out.
        Exception: If save fails after all retries.
    """
    try:
        await asyncio.wait_for(
            vector_store.save(index_path, namespace=namespace),
            timeout=10.0,
        )
    except TimeoutError:
        raise AdapterError("Index save timed out, will retry") from None
