"""Pipeline step registry."""

from __future__ import annotations

import threading
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = ["get_step", "step"]

_step_registry: dict[str, Callable[..., Awaitable[Any]]] = {}
_lock: threading.Lock = threading.Lock()


def step(
    name: str,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Register a pipeline step by name.

    Args:
        name: Unique step identifier.

    Returns:
        Decorator that registers the function.
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        with _lock:
            if name in _step_registry:
                warnings.warn(
                    f"Step {name!r} already registered; overwriting",
                    stacklevel=2,
                )
            _step_registry[name] = fn
        return fn

    return decorator


def get_step(name: str) -> Callable[..., Awaitable[Any]]:
    """Retrieve a registered step.

    Args:
        name: Step identifier.

    Returns:
        Registered step function.

    Raises:
        ValueError: If step not found.
    """
    with _lock:
        if name not in _step_registry:
            raise ValueError(f"Unknown step: {name}")
        return _step_registry[name]
