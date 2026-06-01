"""Async JSONL metrics logging."""

from __future__ import annotations

import asyncio
import contextlib
import json
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles

from ai_assistant.core.logger import get_logger

__all__ = [
    "get_current_metrics",
    "MetricsLogger",
    "record_metric",
]

_logger = get_logger("metrics")


class MetricsLogger:
    """Non-blocking JSONL metrics logger using asyncio queue + background task."""

    def __init__(self, path: str | Path = "./data/metrics.jsonl") -> None:
        self._base_path = Path(path)
        self._queue: asyncio.Queue[dict[str, Any] | None] | None = None
        self._task: asyncio.Task[None] | None = None
        self._logger = _logger

    def _current_path(self) -> Path:
        """Return the rotated path for today's date."""
        today = datetime.now(UTC).date().isoformat()
        return (
            self._base_path.parent
            / f"{self._base_path.stem}-{today}{self._base_path.suffix}"
        )

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
                path = self._current_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(path, mode="a", encoding="utf-8") as f:
                    await f.write(payload)
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


# Fallback for Python builds without ContextVar(default_factory=...)
try:
    _request_metrics: ContextVar[dict[str, Any] | None] = ContextVar(
        "request_metrics",
        default_factory=dict,  # type: ignore[call-overload]
    )
except TypeError:
    _request_metrics = ContextVar("request_metrics", default=None)


def record_metric(key: str, value: Any) -> None:
    """Record a metric for the current request context.

    Raises:
        TypeError: If *value* is not a JSON-serializable primitive.
    """
    if not isinstance(value, (str, int, float, bool, type(None), list, dict)):
        raise TypeError(
            f"Metric value must be a JSON-serializable primitive, "
            f"got {type(value).__name__} for key {key!r}"
        )
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
