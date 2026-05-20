"""Storage ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IChatStorage(ABC):
    """Chat history persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def save_message(
        self, conversation_id: str, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]: ...


class ISettingsStorage(ABC):
    """Settings persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def get(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    async def set(self, key: str, value: Any) -> None: ...
