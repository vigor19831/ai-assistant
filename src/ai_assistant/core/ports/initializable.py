"""Initializable port — for adapters requiring explicit setup."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["IInitializable"]


class IInitializable(ABC):
    """Mixin protocol for adapters that need database or resource initialization."""

    @abstractmethod
    async def init_db(self) -> None:
        """Initialize persistent storage or other resources."""
        ...
