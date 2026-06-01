"""Async circuit breaker for transient fault protection."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, TypeVar

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "with_circuit_breaker",
]

F = TypeVar("F", bound=Callable[..., Any])


class CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Tuning for the circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    expected_exception: tuple[type[Exception], ...] = (Exception,)


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is OPEN — fast fail without calling the adapter."""


class CircuitBreaker:
    """Async-safe circuit breaker.

    Compose **outside** retry logic so that OPEN state short-circuits
    before any retry attempts::

        @with_circuit_breaker(cb)
        @with_retry(max_retries=3)
        async def complete(...): ...
    """

    def __init__(self, config: CircuitBreakerConfig | None = None) -> None:
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def check(self) -> None:
        """Raise CircuitBreakerOpenError if circuit is OPEN and not ready for retry."""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                else:
                    assert self._last_failure_time is not None
                    remaining = self.config.recovery_timeout - (
                        time.monotonic() - self._last_failure_time
                    )
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker OPEN for {remaining:.1f}s"
                    )

    async def record_failure(self) -> None:
        """Trip the breaker on a failed call. Thread-safe."""
        async with self._lock:
            self._record_failure()

    async def record_success(self) -> None:
        """Notify the breaker of a successful call. Thread-safe."""
        async with self._lock:
            self._record_success()

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke *func* if the circuit allows it."""
        await self.check()
        try:
            result = await func(*args, **kwargs)
        except self.config.expected_exception:
            await self.record_failure()
            raise
        await self.record_success()
        return result

    def _should_attempt_reset(self) -> bool:
        if self._last_failure_time is None:
            return True
        return (
            time.monotonic() - self._last_failure_time >= self.config.recovery_timeout
        )

    def _record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._failure_count = 1
        elif self._failure_count >= self.config.failure_threshold:
            self._state = CircuitState.OPEN

    def _record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.half_open_max_calls:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
        else:
            self._failure_count = 0


def with_circuit_breaker(cb: CircuitBreaker) -> Callable[[F], F]:
    """Decorator wrapping an async callable with *cb*.

    Intended use: outermost decorator so that OPEN circuit aborts
    immediately without triggering retries.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await cb.call(func, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
