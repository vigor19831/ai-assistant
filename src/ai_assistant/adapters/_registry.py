"""Adapter registry — explicit dict, no reflection.

Used by @register decorator and factory.py.
Core is stdlib-only, so this lives in adapters/ (not core/).
"""

from __future__ import annotations

from collections.abc import Callable

__all__ = ["register", "get_registry"]

_REGISTRY: dict[str, dict[str, type]] = {}


def register(port: str, name: str) -> Callable[[type], type]:
    """Register an adapter class under a port and name.

    Usage:
        @register("llm", "mock")
        class MockLLM(ILLM): ...
    """

    def decorator(cls: type) -> type:
        _REGISTRY.setdefault(port, {})[name] = cls
        return cls

    return decorator


def get_registry() -> dict[str, dict[str, type]]:
    """Return a shallow copy of the registry for inspection."""
    return {port: dict(adapters) for port, adapters in _REGISTRY.items()}
