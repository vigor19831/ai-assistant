"""Storage ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = ["IChatStorage", "ISettingsStorage"]


class IChatStorage(ABC):
    """Chat history persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def save_message(self, conversation_id: str, message: dict[str, Any]) -> None:
        """Persist a single message for a conversation."""
        ...

    @abstractmethod
    async def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return recent messages for a conversation, oldest first."""
        ...


class ISettingsStorage(ABC):
    """Settings persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a setting value or *default* if absent."""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        """Persist a setting value."""
        ...
