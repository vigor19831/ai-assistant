"""Transport port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ITransport(ABC):
    """HTTP/WS server abstraction."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
