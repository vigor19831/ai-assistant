"""Pipeline step registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

_step_registry: dict[str, Callable[..., Awaitable[Any]]] = {}


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
    if name not in _step_registry:
        raise ValueError(f"Unknown step: {name}")
    return _step_registry[name]
