"""Async JSONL metrics logging."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Final

from ai_assistant.core.logger import get_logger

__all__ = [
    "get_current_metrics",
    "get_metrics_logger",
    "MetricsLogger",
    "record_metric",
]

_logger = get_logger("metrics")
_lock: Final = threading.Lock()
_metrics_logger: MetricsLogger | None = None


class MetricsLogger:
    """Non-blocking JSONL metrics logger using asyncio queue + background task."""

    def __init__(self, path: str | Path = "./data/metrics.jsonl") -> None:
        self._path = Path(path)
        self._queue: asyncio.Queue[dict[str, Any] | None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._logger = _logger

    def start(self) -> None:
        """Start background writer task."""
        if self._task is not None and not self._task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "MetricsLogger.start() must be called within a running event loop"
            ) from exc
        self._queue = asyncio.Queue(maxsize=1000)
        self._task = loop.create_task(self._worker())

    def _append_line(self, line: str) -> None:
        """Synchronous durable file append."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    async def _worker(self) -> None:
        """Consume queue and append JSON lines."""
        if self._queue is None:
            return
        while True:
            item = await self._queue.get()
            if item is None:
                break
            try:
                payload = json.dumps(item, ensure_ascii=False, default=str) + "\n"
                await asyncio.to_thread(self._append_line, payload)
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as exc:
                self._logger.warning("Metrics write failed: %s", exc)

    def log(self, data: dict[str, Any]) -> None:
        """Enqueue metric record (non-blocking)."""
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            _logger.warning("Metrics queue full; dropping record")

    async def stop(self) -> None:
        """Signal shutdown and await worker completion."""
        if self._queue is None:
            return
        for _ in range(3):
            try:
                self._queue.put_nowait(None)
                break
            except asyncio.QueueFull:
                try:
                    await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
        else:
            _logger.warning("Cannot enqueue sentinel; cancelling worker")
            if self._task and not self._task.done():
                self._task.cancel()

        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._logger.warning("Metrics worker stop timed out")
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._logger.warning("Metrics worker stop failed: %s", exc)

        self._queue = None
        self._task = None


def get_metrics_logger() -> MetricsLogger:
    """Thread-safe singleton accessor."""
    global _metrics_logger
    with _lock:
        if _metrics_logger is None:
            _metrics_logger = MetricsLogger()
    return _metrics_logger


# Fallback for Python builds without ContextVar(default_factory=...)
# See PEP 567; default_factory added in 3.13.1 but some builds lack it.
try:
    _request_metrics: ContextVar[dict[str, Any] | None] = ContextVar(
        "request_metrics",
        default_factory=dict,  # type: ignore[call-overload]
    )
except TypeError:
    _request_metrics = ContextVar("request_metrics", default=None)


def record_metric(key: str, value: Any) -> None:
    """Record a metric for the current request context."""
    metrics = _request_metrics.get()
    if metrics is None:
        metrics = {}
    metrics[key] = value
    _request_metrics.set(metrics)


def get_current_metrics() -> dict[str, Any]:
    """Get metrics collected for the current request."""
    metrics = _request_metrics.get()
    if metrics is None:
        return {}
    return metrics.copy()
