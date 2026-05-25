"""Application lifespan — startup/shutdown with graceful cleanup."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from ai_assistant.api.deps import init_adapters
from ai_assistant.core.config import AppConfig, load_config
from ai_assistant.core.logger import get_logger, setup_logging
from ai_assistant.core.metrics import get_metrics_logger
from ai_assistant.core.registry import create as registry_create  # noqa: F401 — для тестируемости

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
    setup_logging(
        level="DEBUG" if config.debug else "INFO",
        log_file=getattr(config, "log_file", "./data/app.log"),
    )
    get_metrics_logger().start()
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
        await get_metrics_logger().stop()
        return

    await get_metrics_logger().stop()

    for attr, name in (
        (state.llm, "llm"),
        (state.embedder, "embedder"),
    ):
        if attr and hasattr(attr, "shutdown"):
            try:
                await attr.shutdown()
            except Exception as exc:
                logger.warning("%s shutdown failed: %s", name, exc)

    index_path = getattr(config.vector_store, "index_path", None)
    if index_path and state.vector_store:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await state.vector_store.save(index_path, namespace=ns)
        except Exception as exc:
            logger.warning("Index save failed: %s", exc)
