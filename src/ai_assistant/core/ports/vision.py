"""Vision port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = ["IVisionProcessor"]


class IVisionProcessor(ABC):
    """Image understanding."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def describe(self, image_base64: str, prompt: str | None = None) -> str:
        """Describe an image given base64 data or URL.

        Args:
            image_base64: Base64-encoded image or image URL.
            prompt: Optional prompt to guide description.

        Returns:
            Textual description of the image.
        """
        ...
