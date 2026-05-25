"""Transport port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = ["ITransport"]


class ITransport(ABC):
    """HTTP/WS server abstraction."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def start(self) -> None:
        """Start the transport server."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the transport server."""
        ...
