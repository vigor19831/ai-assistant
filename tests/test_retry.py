"""Tests for core/retry.py.

Covers: async retry, backoff math, jitter bounds, permanent-error
short-circuit, non-retryable base exceptions, max_delay cap, and
exhaustion.

Design: deterministic unit tests, no wall-clock asserts.
All asyncio.sleep is mocked via pytest.MonkeyPatch fixture.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ai_assistant.core.domain.configs import RetryConfig
from ai_assistant.core.retry import retry_with_config, with_retry


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def instrumented_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Return a list that captures all asyncio.sleep delays. No real sleep."""
    delays: list[float] = []

    async def _async_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _async_sleep)
    return delays


# ---------------------------------------------------------------------------
# Basic retry behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_success_first_attempt() -> None:
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
async def test_retry_recovers_after_transient_failures() -> None:
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
async def test_retry_exhausts_max_retries() -> None:
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


# ---------------------------------------------------------------------------
# Non-retryable exceptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_no_retry_on_permanent_error() -> None:
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
async def test_retry_no_retry_on_keyboard_interrupt() -> None:
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
async def test_retry_no_retry_on_timeout_error() -> None:
    """Given: function raises TimeoutError.
    When: called.
    Then: propagates immediately, no retries.
    """
    calls: list[int] = []

    @with_retry(max_retries=3)
    async def fn() -> str:
        calls.append(len(calls) + 1)
        raise TimeoutError("timed out")

    with pytest.raises(TimeoutError, match="timed out"):
        await fn()
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Parametrised permanent-error coverage
# ---------------------------------------------------------------------------

_PERMANENT_ERROR_CASES: list[type[Exception]] = [
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    ModuleNotFoundError,
]


@pytest.mark.parametrize("exc_cls", _PERMANENT_ERROR_CASES)
@pytest.mark.asyncio
async def test_permanent_errors_are_non_retryable(exc_cls: type[Exception]) -> None:
    """Given: any exception in _PERMANENT_ERRORS.
    When: raised by decorated function.
    Then: no retries occur.
    """
    calls: list[int] = []

    @with_retry(max_retries=5)
    async def fn() -> str:
        calls.append(len(calls) + 1)
        raise exc_cls("permanent")

    with pytest.raises(exc_cls):
        await fn()
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Backoff and delay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_backoff_increases_delay(
    instrumented_sleep: list[float],
) -> None:
    """Given: function fails twice.
    When: delay=0.1, backoff=2.0.
    Then: second retry waits longer than first.
    """
    tracker = _CallTracker(fail_n=2)

    @with_retry(max_retries=3, delay=0.1, backoff=2.0)
    async def fn() -> str:
        return await tracker.async_call()

    await fn()
    assert len(instrumented_sleep) == 2
    assert instrumented_sleep[1] > instrumented_sleep[0]
    assert abs(instrumented_sleep[0] - 0.1) < 0.0001
    assert abs(instrumented_sleep[1] - 0.2) < 0.0001


@pytest.mark.asyncio
async def test_retry_max_delay_cap(
    instrumented_sleep: list[float],
) -> None:
    """Given: backoff would exceed max_delay.
    When: delay=1.0, backoff=10.0, max_delay=5.0.
    Then: delays are capped at 5.0.
    """
    tracker = _CallTracker(fail_n=7)

    @with_retry(max_retries=6, delay=1.0, backoff=10.0, max_delay=5.0)
    async def fn() -> str:
        return await tracker.async_call()

    with pytest.raises(RuntimeError):
        await fn()
    assert all(d <= 5.0 for d in instrumented_sleep)


# ---------------------------------------------------------------------------
# Jitter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_jitter_exact_with_fixed_seed(
    instrumented_sleep: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given: jitter=True with deterministic random.
    When: function fails 4 times.
    Then: delays follow jitter-before-cap formula exactly.
    """
    tracker = _CallTracker(fail_n=5)

    # Fix random.uniform to return midpoint for deterministic test
    monkeypatch.setattr(random, "uniform", lambda a, b: (a + b) / 2)

    @with_retry(max_retries=4, delay=1.0, jitter=True)
    async def fn() -> str:
        return await tracker.async_call()

    with pytest.raises(RuntimeError):
        await fn()

    assert len(instrumented_sleep) == 4
    # uniform(0, current_delay) with midpoint → current_delay / 2
    # attempt 0: current_delay=1.0  → 0.5
    # attempt 1: current_delay=2.0  → 1.0
    # attempt 2: current_delay=4.0  → 2.0
    # attempt 3: current_delay=8.0  → 4.0
    expected = [0.5, 1.0, 2.0, 4.0]
    for actual, exp in zip(instrumented_sleep, expected):
        assert abs(actual - exp) < 0.0001


@pytest.mark.asyncio
async def test_retry_jitter_randomness_bounds(
    instrumented_sleep: list[float],
) -> None:
    """Given: jitter=True with real random.
    When: function fails 4 times.
    Then: each delay is in [0, nominal_delay].
    """
    tracker = _CallTracker(fail_n=5)

    @with_retry(max_retries=4, delay=1.0, jitter=True)
    async def fn() -> str:
        return await tracker.async_call()

    with pytest.raises(RuntimeError):
        await fn()

    assert len(instrumented_sleep) == 4
    expected_max = [1.0, 2.0, 4.0, 8.0]
    for i, (d, max_d) in enumerate(zip(instrumented_sleep, expected_max)):
        assert 0.0 <= d <= max_d, f"delay[{i}]={d} not in [0, {max_d}]"


@pytest.mark.asyncio
async def test_retry_jitter_with_max_delay(
    instrumented_sleep: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Given: jitter=True and max_delay=3.0.
    When: current_delay exceeds max_delay.
    Then: jittered value is capped to max_delay.
    """
    tracker = _CallTracker(fail_n=3)

    # Force jitter to return value above max_delay to test cap
    call_count = 0

    def _forced_jitter(a: float, b: float) -> float:
        nonlocal call_count
        call_count += 1
        # Return value above max_delay (3.0) on second retry
        return b + 1.0  # always > max_delay

    monkeypatch.setattr(random, "uniform", _forced_jitter)

    @with_retry(max_retries=2, delay=1.0, backoff=10.0, max_delay=3.0, jitter=True)
    async def fn() -> str:
        return await tracker.async_call()

    with pytest.raises(RuntimeError):
        await fn()

    # attempt 0: current_delay=1.0, jitter=2.0, cap=min(2.0,3.0)=2.0
    # attempt 1: current_delay=10.0, jitter=11.0, cap=min(11.0,3.0)=3.0
    assert len(instrumented_sleep) == 2
    assert abs(instrumented_sleep[0] - 2.0) < 0.0001
    assert abs(instrumented_sleep[1] - 3.0) < 0.0001


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_zero_max_retries() -> None:
    """Given: max_retries=0.
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


# ---------------------------------------------------------------------------
# retry_with_config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retry_with_config_same_behavior_as_decorator(
    instrumented_sleep: list[float],
) -> None:
    """retry_with_config and @with_retry must use shared _async_retry_loop."""
    call_count = 0

    async def _fail_twice() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("fail")
        return "ok"

    config = RetryConfig(max_retries=2, delay=0.01, backoff=1.0, jitter=False)

    # retry_with_config
    result = await retry_with_config(_fail_twice, config)
    assert result == "ok"
    assert call_count == 3

    # @with_retry with identical params
    call_count = 0

    @with_retry(max_retries=2, delay=0.01, backoff=1.0, jitter=False)
    async def _decorated() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("fail")
        return "ok"

    result = await _decorated()
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_with_config_permanent_error_not_retried() -> None:
    """ValueError must not be retried via retry_with_config."""
    coro = AsyncMock(side_effect=ValueError("permanent"))
    config = RetryConfig(max_retries=2, delay=0.01, backoff=1.0, jitter=False)

    with pytest.raises(ValueError):
        await retry_with_config(coro, config)

    assert coro.call_count == 1


@pytest.mark.asyncio
async def test_retry_with_config_timeout_error_not_retried() -> None:
    """TimeoutError must not be retried via retry_with_config."""
    coro = AsyncMock(side_effect=TimeoutError("timed out"))
    config = RetryConfig(max_retries=5, delay=0.01, backoff=1.0, jitter=False)

    with pytest.raises(TimeoutError):
        await retry_with_config(coro, config)

    assert coro.call_count == 1


@pytest.mark.asyncio
async def test_retry_with_config_uses_retry_config_type() -> None:
    """retry_with_config must accept real RetryConfig with all fields set."""
    call_count = 0

    async def _fail_once() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("fail")
        return "ok"

    config = RetryConfig(
        max_retries=1,
        delay=0.001,
        backoff=1.0,
        max_delay=0.5,
        jitter=False,
    )
    result = await retry_with_config(_fail_once, config)
    assert result == "ok"
    assert call_count == 2
