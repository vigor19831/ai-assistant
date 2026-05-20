"""Retry decorator."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

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
    max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0
) -> Callable[[F], F]:
    """Decorator adding exponential backoff retry.

    Does NOT retry exceptions in _PERMANENT_ERRORS.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_exception if last_exception else RuntimeError("Retry exhausted")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        import time

                        time.sleep(current_delay)
                        current_delay *= backoff
            raise last_exception if last_exception else RuntimeError("Retry exhausted")

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
