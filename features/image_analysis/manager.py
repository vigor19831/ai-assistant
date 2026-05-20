"""Image analysis manager."""

from __future__ import annotations

from typing import Any

from core.domain.messages import AssistantMessage, ImagePayload, UserMessage


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
            result = await self.vision.describe(img_input, prompt=prompt)
            if result and result.strip():
                return AssistantMessage(text=result)

        if self.llm and image:
            user_msg = UserMessage(text=prompt, image=image)
            return await self.llm.complete([user_msg])

        return AssistantMessage(
            text=(
                "Vision analysis not available. "
                "Enable vision in config or use a multimodal LLM."
            )
        )
