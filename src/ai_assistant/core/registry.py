"""Adapter registry — sacred, immutable."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["create", "list_adapters", "register"]

_registry: dict[str, dict[str, Callable[..., Any]]] = {}


def register(port: str, name: str) -> Callable[[type], type]:
    """Decorator to register an adapter implementation.

    Args:
        port: Port category (e.g., "llm", "embedder").
        name: Adapter identifier (e.g., "openai_compatible").

    Returns:
        Decorator function.
    """

    def decorator(cls: type) -> type:
        _registry.setdefault(port, {})[name] = cls
        return cls

    return decorator


def create(port: str, name: str, config: Any) -> Any:
    """Instantiate a registered adapter.

    Args:
        port: Port category.
        name: Registered adapter name.
        config: Configuration object passed to adapter __init__.

    Returns:
        Adapter instance.

    Raises:
        ValueError: If port/name not found.
    """
    if port not in _registry or name not in _registry[port]:
        raise ValueError(f"No adapter registered for {port}/{name}")
    return _registry[port][name](config)


def list_adapters(port: str | None = None) -> dict[str, list[str]] | list[str]:
    """List registered adapters."""
    if port is None:
        return {p: list(adapters.keys()) for p, adapters in _registry.items()}
    if port in _registry:
        return list(_registry[port].keys())
    return []
