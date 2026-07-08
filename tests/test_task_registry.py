"""Tests for TaskRegistry — background task lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import create_autospec

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
    result = await task
    assert result == "done"
    # After completion, registry should be empty
    assert len(registry.get_tasks()) == 0


async def test_spawn_stores_metadata(registry: TaskRegistry) -> None:
    """trace_id and name are preserved in the registry snapshot."""
    done = asyncio.Event()

    async def _coro() -> None:
        await done.wait()

    task = registry.spawn(_coro, trace_id="t1-meta", name="meta_task")
    tasks = registry.get_tasks()
    assert len(tasks) == 1
    record = next(iter(tasks))
    assert record.task is task
    assert record.trace_id == "t1-meta"
    assert record.name == "meta_task"
    assert record.started_at > 0
    done.set()
    await task


async def test_get_tasks_returns_snapshot(registry: TaskRegistry) -> None:
    """get_tasks() returns a copy; mutating it does not affect the registry."""
    done = asyncio.Event()

    async def _coro() -> None:
        await done.wait()

    registry.spawn(_coro, trace_id="t2", name="sleepy")
    tasks = registry.get_tasks()
    assert len(tasks) == 1

    # Mutating the returned set must not affect the registry.
    tasks.clear()
    assert len(registry.get_tasks()) == 1

    done.set()
    await asyncio.gather(*[r.task for r in registry.get_tasks()])


async def test_spawn_logs_exception_on_failure(
    registry: TaskRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    async def _bad_coro() -> None:
        raise ValueError("intentional failure")

    task = registry.spawn(_bad_coro, trace_id="t3", name="failing")
    # gather with return_exceptions=True ensures done-callback runs
    # before we inspect registry state, without wall-clock yield.
    await asyncio.gather(task, return_exceptions=True)

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

    # Release the coroutine after shutdown starts waiting.
    asyncio.get_running_loop().call_later(0.05, done.set)
    await registry.shutdown(wait_for=1.0)

    assert completed is True
    assert len(registry.get_tasks()) == 0


async def test_shutdown_cancels_on_timeout(registry: TaskRegistry) -> None:
    block = asyncio.Event()

    async def _forever_coro() -> None:
        await block.wait()  # Never set — simulates infinite work

    task = registry.spawn(_forever_coro, trace_id="t5", name="forever")
    # wait_for=0.0 forces immediate timeout; gather will see pending tasks.
    await registry.shutdown(wait_for=0.0)
    assert task.cancelled() is True
    assert len(registry.get_tasks()) == 0


async def test_shutdown_noop_when_empty(registry: TaskRegistry) -> None:
    # Should not raise
    await registry.shutdown(wait_for=1.0)
    assert len(registry.get_tasks()) == 0


def test_task_record_immutable() -> None:
    task_mock = create_autospec(asyncio.Task, instance=True)
    record = TaskRecord(task=task_mock, trace_id="t6", name="recorded")
    assert record.trace_id == "t6"
    assert record.name == "recorded"
    assert record.started_at > 0
