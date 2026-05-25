"""Generic modality processor port — placeholder for future extension."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = ["IModalityProcessor"]


class IModalityProcessor(ABC):
    """Placeholder for future multimodal processor (video, 3D, etc.)."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def process(self, data: Any) -> Any:
        """Process multimodal input."""
        ...
