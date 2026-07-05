"""Centralized background task registry.

Per-application-instance. Created in lifespan, injected via AppState.
Eliminates module-level mutable state and scattered task management.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ai_assistant.core.logger import get_logger

__all__ = ["TaskRecord", "TaskRegistry"]

_logger = get_logger("task_registry")


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """Immutable snapshot of a background task."""

    task: asyncio.Task[Any]
    trace_id: str
    name: str
    started_at: float = field(default_factory=time.time)


class TaskRegistry:
    """Owns all background tasks for one application instance.

    Provides: strong references, exception logging, graceful shutdown.
    Replaces RAGState._tasks and any future ad-hoc task sets.
    """

    def __init__(self) -> None:
        self._tasks: set[TaskRecord] = set()

    def spawn(
        self,
        coro_factory: Callable[[], Any],
        *,
        trace_id: str = "",
        name: str = "",
    ) -> asyncio.Task[Any]:
        """Launch a coroutine in the background.

        Args:
            coro_factory: Zero-argument callable returning a coroutine.
                Thunk pattern prevents accidental pre-execution.
            trace_id: Structured logging trace identifier.
            name: Human-readable task name.

        Returns:
            The created Task (for tests and status checks).
        """
        task = asyncio.create_task(coro_factory(), name=name)

        record = TaskRecord(task=task, trace_id=trace_id, name=name)

        self._tasks.add(record)

        def _on_done(t: asyncio.Task[Any]) -> None:
            self._tasks.discard(record)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                _logger.error(
                    "Background task failed",
                    extra={
                        "trace_id": trace_id,
                        "task_name": name,
                        "error": str(exc),
                    },
                    exc_info=exc,
                )

        task.add_done_callback(_on_done)
        return task

    def get_tasks(self) -> set[TaskRecord]:
        """Return snapshot of active tasks."""
        return set(self._tasks)

    async def shutdown(self, wait_for: float = 30.0) -> None:
        """Gracefully wait for all tasks."""
        if not self._tasks:
            return

        _logger.info(
            "Waiting for background tasks",
            extra={"count": len(self._tasks)},
        )

        tasks = [r.task for r in self._tasks]
        try:
            async with asyncio.timeout(wait_for):
                await asyncio.gather(*tasks, return_exceptions=True)
        except TimeoutError:
            _logger.warning("Background tasks timed out, cancelling")
            for t in tasks:
                if not t.done():
                    t.cancel()
            # Allow cancelled tasks one event loop iteration to handle
            # CancelledError and run their finally blocks.
            pending = [t for t in tasks if not t.done()]
            if pending:
                try:
                    async with asyncio.timeout(5.0):
                        await asyncio.gather(*pending, return_exceptions=True)
                except TimeoutError:
                    _logger.warning(
                        "Cancelled tasks did not finish within 5s",
                        extra={"pending": len(pending)},
                    )
