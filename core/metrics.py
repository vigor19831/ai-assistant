"""Async JSONL metrics logging."""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from core.logger import get_logger


class MetricsLogger:
    """Non-blocking JSONL metrics logger using asyncio queue + background task."""

    def __init__(self, path: str = "./data/metrics.jsonl") -> None:
        self._logger = get_logger("metrics")
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._queue: asyncio.Queue[dict[str, Any] | None] | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start background writer task."""
        if self._task is None or self._task.done():
            self._queue = asyncio.Queue(maxsize=1000)
            self._task = asyncio.create_task(self._worker())

    def _append_line(self, line: str) -> None:
        """Synchronous file append."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)

    async def _worker(self) -> None:
        """Consume queue and append JSON lines."""
        if self._queue is None:
            return
        while True:
            item = await self._queue.get()
            if item is None:
                break
            try:
                line = json.dumps(item, ensure_ascii=False, default=str) + "\n"
                await asyncio.to_thread(self._append_line, line)
            except Exception as exc:
                self._logger.warning("Metrics write failed: %s", exc)

    def log(self, data: dict[str, Any]) -> None:
        """Enqueue metric record (non-blocking)."""
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    async def stop(self) -> None:
        """Signal shutdown and await worker completion."""
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except asyncio.TimeoutError:
                self._logger.warning("Metrics worker stop timed out")
            except Exception as exc:
                self._logger.warning("Metrics worker stop failed: %s", exc)
        self._queue = None
        self._task = None


_metrics_logger: MetricsLogger | None = None


def get_metrics_logger() -> MetricsLogger:
    """Singleton accessor."""
    global _metrics_logger
    if _metrics_logger is None:
        _metrics_logger = MetricsLogger()
    return _metrics_logger


_request_metrics: ContextVar[dict[str, Any]] = ContextVar("request_metrics", default={})


def record_metric(key: str, value: Any) -> None:
    """Record a metric for the current request context."""
    try:
        metrics = _request_metrics.get()
    except LookupError:
        metrics = {}
    metrics[key] = value
    _request_metrics.set(metrics)


def get_current_metrics() -> dict[str, Any]:
    """Get metrics collected for the current request."""
    try:
        return _request_metrics.get().copy()
    except LookupError:
        return {}
