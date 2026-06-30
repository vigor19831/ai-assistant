"""Tests for core/retry.py.

Covers: sync/async retry, backoff math, jitter bounds, permanent-error
short-circuit, max_delay cap, and exhaustion.

Design: deterministic unit tests, no Hypothesis state machine.
State machines add complexity; coverage is achieved via parametrised
test cases.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import pytest

from ai_assistant.core.retry import with_retry, _PERMANENT_ERRORS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CallTracker:
    """Count invocations and optionally fail N times."""

    def __init__(self, fail_n: int = 0, exc: type[Exception] = RuntimeError) -> None:
        self.fail_n = fail_n
        self.exc = exc
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def async_call(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append((args, kwargs))
        if len(self.calls) <= self.fail_n:
            raise self.exc(f"fail #{len(self.calls)}")
        return "success"

    def sync_call(self, *args: Any, **kwargs: Any) -> str:
        self.calls.append((args, kwargs))
        if len(self.calls) <= self.fail_n:
            raise self.exc(f"fail #{len(self.calls)}")
        return "success"


# ---------------------------------------------------------------------------
# Async tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_success_first_attempt():
    """Given: decorated function succeeds immediately.
    When: called once.
    Then: returns result, no retries.
    """
    tracker = _CallTracker(fail_n=0)

    @with_retry(max_retries=3)
    async def fn(x: int) -> str:
        return await tracker.async_call(x)

    result = await fn(42)
    assert result == "success"
    assert len(tracker.calls) == 1
    assert tracker.calls[0] == ((42,), {})


@pytest.mark.asyncio
async def test_retry_recovers_after_transient_failures():
    """Given: function fails twice then succeeds.
    When: max_retries=3.
    Then: succeeds on 3rd attempt.
    """
    tracker = _CallTracker(fail_n=2)

    @with_retry(max_retries=3, delay=0.01)
    async def fn() -> str:
        return await tracker.async_call()

    result = await fn()
    assert result == "success"
    assert len(tracker.calls) == 3


@pytest.mark.asyncio
async def test_retry_exhausts_max_retries():
    """Given: function always fails.
    When: max_retries=2.
    Then: raises last exception after 3 attempts.
    """
    tracker = _CallTracker(fail_n=10)

    @with_retry(max_retries=2, delay=0.01)
    async def fn() -> str:
        return await tracker.async_call()

    with pytest.raises(RuntimeError, match="fail #3"):
        await fn()
    assert len(tracker.calls) == 3


@pytest.mark.asyncio
async def test_retry_no_retry_on_permanent_error():
    """Given: function raises ValueError (permanent).
    When: called.
    Then: raises immediately, no retries.
    """
    tracker = _CallTracker(fail_n=10, exc=ValueError)

    @with_retry(max_retries=3)
    async def fn() -> str:
        return await tracker.async_call()

    with pytest.raises(ValueError):
        await fn()
    assert len(tracker.calls) == 1


@pytest.mark.asyncio
async def test_retry_no_retry_on_keyboard_interrupt():
    """Given: function raises KeyboardInterrupt.
    When: called.
    Then: propagates immediately, no retries.
    """
    calls: list[int] = []

    @with_retry(max_retries=3)
    async def fn() -> str:
        calls.append(len(calls) + 1)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        await fn()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_retry_backoff_increases_delay():
    """Given: function fails twice.
    When: delay=0.1, backoff=2.0.
    Then: second retry waits longer than first.
    """
    tracker = _CallTracker(fail_n=2)
    delays: list[float] = []

    original_sleep = asyncio.sleep

    async def _instrumented_sleep(delay: float) -> None:
        delays.append(delay)
        await original_sleep(0.001)  # speed up tests

    @with_retry(max_retries=3, delay=0.1, backoff=2.0)
    async def fn() -> str:
        return await tracker.async_call()

    # Monkey-patch asyncio.sleep for this test
    asyncio.sleep = _instrumented_sleep  # type: ignore[assignment]
    try:
        await fn()
    finally:
        asyncio.sleep = original_sleep  # type: ignore[assignment]

    assert len(delays) == 2
    assert delays[1] > delays[0]
    assert abs(delays[0] - 0.1) < 0.01
    assert abs(delays[1] - 0.2) < 0.01


# ---------------------------------------------------------------------------
# Sync tests
# ---------------------------------------------------------------------------

def test_retry_sync_version():
    """Given: synchronous function with transient failures.
    When: decorated with @with_retry.
    Then: retries work identically to async version.
    """
    tracker = _CallTracker(fail_n=2)

    @with_retry(max_retries=3, delay=0.01)
    def fn() -> str:
        return tracker.sync_call()

    result = fn()
    assert result == "success"
    assert len(tracker.calls) == 3


def test_retry_max_delay_cap():
    """Given: backoff would exceed max_delay.
    When: delay=1.0, backoff=10.0, max_delay=5.0.
    Then: delays are capped at 5.0.
    """
    tracker = _CallTracker(fail_n=7)
    delays: list[float] = []
    original_sleep = time.sleep

    def _instrumented_sleep(delay: float) -> None:
        delays.append(delay)
        # no actual sleep to keep test fast

    @with_retry(max_retries=6, delay=1.0, backoff=10.0, max_delay=5.0)
    def fn() -> str:
        return tracker.sync_call()

    time.sleep = _instrumented_sleep  # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError):
            fn()
    finally:
        time.sleep = original_sleep  # type: ignore[assignment]

    assert all(d <= 5.0 for d in delays)


def test_retry_jitter_bounds():
    """Given: jitter=True.
    When: function fails.
    Then: actual delay is in [0, nominal_delay] for each retry.
    """
    tracker = _CallTracker(fail_n=5)
    delays: list[float] = []
    original_sleep = time.sleep

    def _instrumented_sleep(delay: float) -> None:
        delays.append(delay)

    @with_retry(max_retries=4, delay=1.0, jitter=True)
    def fn() -> str:
        return tracker.sync_call()

    time.sleep = _instrumented_sleep  # type: ignore[assignment]
    try:
        with pytest.raises(RuntimeError):
            fn()
    finally:
        time.sleep = original_sleep  # type: ignore[assignment]

    assert len(delays) == 4
    # Jitter: each delay is in [0, current_delay]
    # current_delay starts at 1.0, then doubles: 1.0, 2.0, 4.0, 8.0
    expected_max = [1.0, 2.0, 4.0, 8.0]
    for i, (d, max_d) in enumerate(zip(delays, expected_max)):
        assert 0.0 <= d <= max_d, f"delay[{i}]={d} not in [0, {max_d}]"


# ---------------------------------------------------------------------------
# Permanent errors
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("exc_cls", _PERMANENT_ERRORS)
def test_all_permanent_errors_are_non_retryable(exc_cls: type[Exception]) -> None:
    """Given: any exception in _PERMANENT_ERRORS.
    When: raised by decorated function.
    Then: no retries occur.
    """
    calls: list[int] = []

    @with_retry(max_retries=5)
    def fn() -> str:
        calls.append(len(calls) + 1)
        raise exc_cls("permanent")

    with pytest.raises(exc_cls):
        fn()
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_retry_zero_max_retries():
    """Given: max_retries=0.
    When: function fails.
    Then: raises after 1 attempt.
    """
    tracker = _CallTracker(fail_n=1)

    @with_retry(max_retries=0, delay=0.01)
    def fn() -> str:
        return tracker.sync_call()

    with pytest.raises(RuntimeError):
        fn()
    assert len(tracker.calls) == 1


@pytest.mark.asyncio
async def test_retry_async_zero_max_retries():
    """Given: async function, max_retries=0.
    When: function fails.
    Then: raises after 1 attempt.
    """
    tracker = _CallTracker(fail_n=1)

    @with_retry(max_retries=0, delay=0.01)
    async def fn() -> str:
        return await tracker.async_call()

    with pytest.raises(RuntimeError):
        await fn()
    assert len(tracker.calls) == 1


# ---------- retry_with_config must use shared logic ----------
from unittest.mock import AsyncMock

import pytest

from ai_assistant.core.domain.configs import RetryConfig
from ai_assistant.core.retry import retry_with_config, with_retry


class _FakeConfig:
    max_retries = 2
    delay = 0.01
    backoff = 1.0
    max_delay = None
    jitter = False


async def test_retry_with_config_same_behavior_as_decorator():
    """retry_with_config and @with_retry must behave identically."""
    call_count = 0

    async def _fail_twice():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("fail")
        return "ok"

    # retry_with_config
    result = await retry_with_config(_fail_twice, _FakeConfig())
    assert result == "ok"
    assert call_count == 3

    # @with_retry
    call_count = 0

    @with_retry(max_retries=2, delay=0.01, backoff=1.0, jitter=False)
    async def _decorated():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("fail")
        return "ok"

    result = await _decorated()
    assert result == "ok"
    assert call_count == 3


async def test_retry_with_config_permanent_error_not_retried():
    """ValueError must not be retried."""
    coro = AsyncMock(side_effect=ValueError("permanent"))

    with pytest.raises(ValueError):
        await retry_with_config(coro, _FakeConfig())

    assert coro.call_count == 1
