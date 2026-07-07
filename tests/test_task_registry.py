"""Tests for TaskRegistry — background task lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from ai_assistant.core.task_registry import TaskRecord, TaskRegistry


@pytest.fixture
def registry() -> TaskRegistry:
    return TaskRegistry()


async def test_spawn_creates_task(registry: TaskRegistry) -> None:
    async def _coro() -> str:
        return "done"

    task = registry.spawn(_coro, trace_id="t1", name="test_task")
    assert isinstance(task, asyncio.Task)
    assert task.get_name() == "test_task"
    await task
    # After completion, registry should be empty
    assert len(registry.get_tasks()) == 0


async def test_get_tasks_returns_snapshot(registry: TaskRegistry) -> None:
    done = asyncio.Event()

    async def _coro() -> None:
        await done.wait()

    task = registry.spawn(_coro, trace_id="t2", name="sleepy")
    tasks = registry.get_tasks()
    assert len(tasks) == 1
    record = next(iter(tasks))
    assert record.task is task
    assert record.trace_id == "t2"
    assert record.name == "sleepy"
    assert record.started_at > 0
    # Signal completion to avoid dangling task
    done.set()
    await task


async def test_spawn_logs_exception_on_failure(
    registry: TaskRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    async def _bad_coro() -> None:
        raise ValueError("intentional failure")

    task = registry.spawn(_bad_coro, trace_id="t3", name="failing")
    with pytest.raises(ValueError):
        await task

    # Registry should be empty after failure
    assert len(registry.get_tasks()) == 0
    # Exception should be logged
    assert "Background task failed" in caplog.text
    assert "intentional failure" in caplog.text
    # trace_id is in extra fields, not in caplog.text — check records
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    assert getattr(error_records[0], "trace_id", None) == "t3"


async def test_shutdown_waits_for_tasks(registry: TaskRegistry) -> None:
    completed = False
    done = asyncio.Event()

    async def _slow_coro() -> None:
        nonlocal completed
        await done.wait()
        completed = True

    registry.spawn(_slow_coro, trace_id="t4", name="slow")
    done.set()
    await registry.shutdown(wait_for=1.0)
    assert completed is True
    assert len(registry.get_tasks()) == 0


async def test_shutdown_cancels_on_timeout(registry: TaskRegistry) -> None:
    forever = asyncio.Event()

    async def _forever_coro() -> None:
        await forever.wait()  # Never set — simulates infinite work

    task = registry.spawn(_forever_coro, trace_id="t5", name="forever")
    await registry.shutdown(wait_for=0.01)
    assert task.cancelled() is True
    assert len(registry.get_tasks()) == 0


async def test_shutdown_noop_when_empty(registry: TaskRegistry) -> None:
    # Should not raise
    await registry.shutdown(wait_for=1.0)
    assert len(registry.get_tasks()) == 0


def test_task_record_immutable() -> None:
    task_mock = MagicMock(spec=asyncio.Task)
    record = TaskRecord(task=task_mock, trace_id="t6", name="recorded")
    assert record.trace_id == "t6"
    assert record.name == "recorded"
    assert record.started_at > 0
