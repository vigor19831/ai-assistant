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
from ai_assistant.core.ports import IClosable

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

    # Mount static files (safe to call here, not middleware)
    from ai_assistant.main import _mount_static

    _mount_static(app, config)

    log_file = getattr(config, "log_file", None)
    if log_file is None:
        log_file = "./data/app.log"
    setup_logging(
        level="DEBUG" if getattr(config, "debug", False) else "INFO",
        log_file=log_file,
    )

    if config.security.api_key and get_expected_api_key() is None:
        set_api_key(config.security.api_key)

    state = await init_adapters(config)
    app.state.app_state = state

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
    state = getattr(app.state, "app_state", None)
    if state is None:
        logger.warning("No app state found during shutdown")
        return

    # 1. Persist indices FIRST — metrics/adapter shutdown may block/hang
    vs_cfg = getattr(config, "vector_store", None)
    index_path = vs_cfg.index_path if vs_cfg is not None else None
    if index_path and state.vector_store is not None:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await state.vector_store.save(index_path, namespace=ns)
                logger.info("Index saved: %s/%s", index_path, ns)
            logger.info("Indices persisted: %d namespace(s)", len(namespaces))
        except Exception:
            logger.exception("Index save failed")

    # 2. Graceful adapter shutdown
    for attr, name in (
        (state.llm, "llm"),
        (state.embedder, "embedder"),
        (state.vector_store, "vector_store"),
    ):
        if attr is not None and isinstance(attr, IClosable):
            try:
                await attr.shutdown()
            except Exception:
                logger.exception("%s shutdown failed", name)
