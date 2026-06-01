"""Versioned prompt loader."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_env_cache: dict[str, Environment] = {}


def _make_hashable(value: Any) -> Any:
    """Convert a value into a hashable form for cache keys."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_make_hashable(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in value.items()))
    if hasattr(value, "__dataclass_fields__"):
        return tuple(
            (k, _make_hashable(getattr(value, k, None)))
            for k in sorted(value.__dataclass_fields__.keys())
        )
    return str(value)


def _kwargs_to_tuple(kwargs: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Convert kwargs dict into a hashable tuple."""
    return tuple(sorted((k, _make_hashable(v)) for k, v in kwargs.items()))


@lru_cache(maxsize=256)
def _render(name: str, version: str, kwargs_tuple: tuple[tuple[str, Any], ...]) -> str:
    """Render a Jinja2 template with LRU-cached result."""
    base = Path(__file__).parent / version
    if not base.exists():
        raise ValueError(f"Prompt version directory not found: {base}")

    env = _env_cache.get(version)
    if env is None:
        env = Environment(
            loader=FileSystemLoader(str(base)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        _env_cache[version] = env

    kwargs = dict(kwargs_tuple)
    return env.get_template(f"{name}.j2").render(**kwargs)


def get_prompt(name: str, version: str = "v1", **kwargs: Any) -> str:
    """Load and render a Jinja2 prompt template.

    Args:
        name: Template filename without .j2 extension.
        version: Prompt version directory (e.g., "v1", "v2").
        **kwargs: Template variables.

    Returns:
        Rendered prompt string.
    """
    return _render(name, version, _kwargs_to_tuple(kwargs))
