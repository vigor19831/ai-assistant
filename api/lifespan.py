"""Application lifespan — startup/shutdown with graceful cleanup."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.deps import init_adapters
from core.config import AppConfig, load_config
from core.logger import get_logger
from core.metrics import get_metrics_logger
from core.registry import create as registry_create  # noqa: F401 — для тестируемости

logger = get_logger("lifespan")


def _load_config() -> AppConfig:
    """Load config from YAML, fallback to env defaults."""
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    return load_config(config_path)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle."""
    config = _load_config()
    get_metrics_logger().start()
    state = await init_adapters(config)
    # Сохраняем state в app для доступа через request.app.state
    app.state.app_state = state

    # Write PID file for stop.py
    import os
    from pathlib import Path
    pid_file = Path("data/server.pid")
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    yield

    state = getattr(app.state, "app_state", state)

    # Clean up PID file
    pid_file = Path("data/server.pid")
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)

    await get_metrics_logger().stop()

    try:
        if state.llm and hasattr(state.llm, "shutdown"):
            try:
                await state.llm.shutdown()
            except Exception as e:
                logger.warning("LLM shutdown failed: %s", e)

        if state.embedder and hasattr(state.embedder, "shutdown"):
            try:
                await state.embedder.shutdown()
            except Exception as e:
                logger.warning("Embedder shutdown failed: %s", e)

        index_path = getattr(config.vector_store, "index_path", None)
        if index_path and state.vector_store:
            try:
                namespaces = await state.vector_store.list_namespaces(index_path)
                for ns in namespaces:
                    await state.vector_store.save(index_path, namespace=ns)
            except Exception as exc:
                logger.warning("Index save failed: %s", exc)
    except RuntimeError:
        pass
