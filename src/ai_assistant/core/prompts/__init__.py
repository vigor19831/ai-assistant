"""Versioned prompt loader."""

from __future__ import annotations

import dataclasses
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_env_cache: dict[str, Environment] = {}


def _make_hashable(value: Any) -> Any:
    visited: set[int] = set()

    def _inner(v: Any) -> Any:
        vid = id(v)
        if vid in visited:
            return "<circular>"
        if type(v) in (str, int, float, bool, type(None)):
            return v
        if type(v) in (list, tuple):
            visited.add(vid)
            try:
                return tuple(_inner(x) for x in v)
            finally:
                visited.discard(vid)
        if type(v) is dict:
            visited.add(vid)
            try:
                return tuple(sorted((k, _inner(val)) for k, val in v.items()))
            finally:
                visited.discard(vid)
        if dataclasses.is_dataclass(v) and type(v) is not type:
            visited.add(vid)
            try:
                fields = v.__dataclass_fields__
                return tuple(
                    (k, _inner(getattr(v, k, None))) for k in sorted(fields.keys())
                )
            finally:
                visited.discard(vid)
        return str(v)

    return _inner(value)


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


def get_prompt(name: str, version: str | None = None, **kwargs: Any) -> str:
    """Load and render a Jinja2 prompt template.

    Args:
        name: Template filename without .j2 extension.
        version: Prompt version directory (e.g., "v1", "v2").
        **kwargs: Template variables.

    Returns:
        Rendered prompt string.

    Raises:
        ValueError: If version is not provided.
    """
    if version is None:
        raise ValueError("prompt version is required")
    return _render(name, version, _kwargs_to_tuple(kwargs))
