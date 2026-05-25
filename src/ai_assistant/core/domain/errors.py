"""Domain exceptions."""

from __future__ import annotations

__all__ = [
    "AdapterError",
    "ConfigurationError",
    "VersionMismatchError",
]


class ConfigurationError(Exception):
    """Invalid configuration."""


class AdapterError(Exception):
    """Adapter operation failed."""


class VersionMismatchError(Exception):
    """Index/model version mismatch."""
