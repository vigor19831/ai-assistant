"""Retry decorator."""

from __future__ import annotations

import asyncio
import functools
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from ai_assistant.core.domain.configs import RetryConfig

__all__ = ["with_retry", "retry_with_config"]

T = TypeVar("T")

F = TypeVar("F", bound=Callable[..., Any])

# Permanent errors that should NOT be retried
_PERMANENT_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    ModuleNotFoundError,
)


def _calculate_sleep(current_delay: float, jitter: bool, max_delay: float | None) -> float:
    """Compute sleep duration with jitter and max_delay cap."""
    sleep_for = current_delay
    if jitter:
        sleep_for = random.uniform(0, sleep_for)
    if max_delay is not None:
        sleep_for = min(sleep_for, max_delay)
    return sleep_for


async def _async_retry_loop(
    coro: Callable[[], Awaitable[T]],
    max_retries: int,
    delay: float,
    backoff: float,
    max_delay: float | None,
    jitter: bool,
) -> T:
    """Shared async retry loop used by @with_retry and retry_with_config."""
    last_exception: Exception | None = None
    current_delay = delay
    for attempt in range(max_retries + 1):
        try:
            return await coro()
        except (SystemExit, KeyboardInterrupt, TimeoutError):
            raise
        except _PERMANENT_ERRORS:
            raise
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                sleep_for = _calculate_sleep(current_delay, jitter, max_delay)
                await asyncio.sleep(sleep_for)
                current_delay *= backoff
    if last_exception is None:
        raise RuntimeError("last_exception is None after retry loop")
    raise last_exception


def with_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float | None = None,
    jitter: bool = False,
) -> Callable[[F], F]:
    """Decorator adding exponential backoff retry.

    Does NOT retry exceptions in _PERMANENT_ERRORS,
    SystemExit, or KeyboardInterrupt.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await _async_retry_loop(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                delay=delay,
                backoff=backoff,
                max_delay=max_delay,
                jitter=jitter,
            )

        return cast("F", async_wrapper)

    return decorator


async def retry_with_config(
    coro: Callable[[], Awaitable[T]], config: RetryConfig
) -> T:
    """Execute coroutine with retry policy from config.

    Delegates to the shared _async_retry_loop to avoid duplicating
    retry logic with @with_retry.
    """
    return await _async_retry_loop(
        coro,
        max_retries=config.max_retries,
        delay=config.delay,
        backoff=config.backoff,
        max_delay=config.max_delay,
        jitter=config.jitter,
    )
