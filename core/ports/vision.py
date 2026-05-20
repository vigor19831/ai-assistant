"""Vision port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IVisionProcessor(ABC):
    """Image understanding."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def describe(self, image_base64: str, prompt: str | None = None) -> str: ...
