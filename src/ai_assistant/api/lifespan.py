"""Application lifespan — startup/shutdown with graceful cleanup."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ai_assistant.api.deps import init_adapters
from ai_assistant.api.security import get_expected_api_key, set_api_key
from ai_assistant.core.config import AppConfig, load_config
from ai_assistant.core.logger import get_logger, setup_logging

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

    from ai_assistant.api.static import _mount_static

    _mount_static(app, config)

    log_file = config.log_file
    if log_file is None:
        log_file = "./data/app.log"
    setup_logging(
        level="DEBUG" if config.debug else "INFO",
        log_file=log_file,
    )

    if config.security.api_key and get_expected_api_key() is None:
        set_api_key(config.security.api_key)

    state = await init_adapters(config)
    app.state.app_state = state

    # Load persisted indices from disk via port contract
    if state.vector_store is not None:
        index_path = state.vector_store.index_path
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await state.vector_store.load(index_path, namespace=ns)
            logger.info(
                "Loaded %d namespace indices from %s", len(namespaces), index_path
            )
        except Exception:
            logger.exception("Index load failed on startup")

    pid_file = Path("data/server.pid")
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(pid_file.write_text, str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write PID file: %s", exc)

    try:
        yield
    finally:
        await _async_cleanup(app, config)
        _cleanup(app, config, pid_file)


def _cleanup(app: FastAPI, config: AppConfig, pid_file: Path) -> None:
    """Synchronous cleanup actions."""
    if pid_file.exists():
        try:
            pid_file.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove PID file: %s", exc)


async def _async_cleanup(app: FastAPI, config: AppConfig) -> None:
    """Async cleanup actions."""
    try:
        state = app.state.app_state
    except AttributeError:
        logger.warning("No app state found during shutdown")
        return

    # 1. Persist indices FIRST — metrics/adapter shutdown may block/hang
    if state.vector_store is not None:
        index_path = state.vector_store.index_path
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            saved = 0
            for ns in namespaces:
                try:
                    await asyncio.wait_for(
                        state.vector_store.save(index_path, namespace=ns),
                        timeout=10.0,
                    )
                    logger.info("Index saved: %s/%s", index_path, ns)
                    saved += 1
                except TimeoutError:
                    logger.warning("Index save timed out: %s/%s", index_path, ns)
            logger.info("Indices persisted: %d/%d namespace(s)", saved, len(namespaces))
        except Exception:
            logger.exception("Index save failed")

    # 2. Graceful adapter shutdown — add new closable adapters here
    adapters = (
        (state.llm, "llm"),
        (state.embedder, "embedder"),
        (state.vector_store, "vector_store"),
        (state.storage, "storage"),
        (state.reranker, "reranker"),
        (state.chunker, "chunker"),
    )

    for adapter, name in adapters:
        if adapter is not None:
            try:
                await adapter.shutdown()
                logger.info("Adapter '%s' shutdown complete", name)
            except Exception:
                logger.exception("Adapter '%s' shutdown failed", name)
