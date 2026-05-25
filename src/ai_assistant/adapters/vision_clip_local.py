"""Local CLIP vision processor — friendly fallback."""

from __future__ import annotations

from typing import Any

from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.vision import IVisionProcessor
from ai_assistant.core.registry import register

__all__ = ["CLIPLocalVision"]

_logger = get_logger("vision.clip_local")


@register("vision", "clip_local")
class CLIPLocalVision(IVisionProcessor):
    """Stub with graceful fallback message."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def describe(self, image_base64: str, prompt: str | None = None) -> str:
        _logger.warning("Vision describe called but CLIP is not configured")
        return (
            "🔧 Vision analysis is not yet configured. "
            "To enable image understanding, install transformers "
            "and set vision.enabled=true in config.yaml."
        )
