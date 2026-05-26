"""Retry decorator."""

from __future__ import annotations

import asyncio
import functools
import inspect
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

__all__ = ["with_retry"]

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
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (SystemExit, KeyboardInterrupt):
                    raise
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        sleep_for = current_delay
                        if jitter:
                            sleep_for = random.uniform(0, sleep_for)
                        if max_delay is not None:
                            sleep_for = min(sleep_for, max_delay)
                        await asyncio.sleep(sleep_for)
                        current_delay *= backoff
            assert last_exception is not None
            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (SystemExit, KeyboardInterrupt):
                    raise
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        sleep_for = current_delay
                        if jitter:
                            sleep_for = random.uniform(0, sleep_for)
                        if max_delay is not None:
                            sleep_for = min(sleep_for, max_delay)
                        time.sleep(sleep_for)
                        current_delay *= backoff
            assert last_exception is not None
            raise last_exception

        wrapper = async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
        return cast("F", wrapper)

    return decorator
