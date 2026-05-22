"""Image analysis manager."""

from __future__ import annotations

from typing import Any

from core.domain.messages import AssistantMessage, ImagePayload, UserMessage
from core.logger import get_logger

__all__ = ["ImageAnalysisManager"]

_logger = get_logger("image.manager")


class ImageAnalysisManager:
    """Routes image analysis to vision processor or multimodal LLM."""

    def __init__(
        self,
        vision: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self.vision = vision
        self.llm = llm

    @property
    def use_llm_vision(self) -> bool:
        return self.vision is None and self.llm is not None

    async def analyze(
        self,
        image_base64: str | None = None,
        image_url: str | None = None,
        prompt: str = "Describe this image.",
    ) -> AssistantMessage:
        """Analyze image via vision processor with LLM fallback."""
        image = None
        if image_base64:
            image = ImagePayload(base64_data=image_base64, mime_type="image/png")
        elif image_url:
            image = ImagePayload(url=image_url)

        if self.vision:
            img_input = image_base64 or image_url or ""
            try:
                result = await self.vision.describe(img_input, prompt=prompt)
                if result and result.strip():
                    return AssistantMessage(text=result)
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as exc:
                _logger.warning(
                    "Vision processor failed (%s), falling back to LLM",
                    exc,
                )

        if self.llm and image:
            user_msg = UserMessage(text=prompt, image=image)
            try:
                return await self.llm.complete([user_msg])
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as exc:
                _logger.error("LLM vision fallback failed: %s", exc)

        return AssistantMessage(
            text=(
                "Vision analysis not available. "
                "Enable vision in config or use a multimodal LLM."
            )
        )
