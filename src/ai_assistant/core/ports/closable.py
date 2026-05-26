"""Closable port — for adapters requiring graceful shutdown."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["IClosable"]


class IClosable(ABC):
    """Mixin protocol for adapters that need explicit cleanup on shutdown."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources and perform graceful shutdown."""
        ...
