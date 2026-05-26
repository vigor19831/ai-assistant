"""RAGPipeline executor — sacred, immutable."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.pipeline import PipelineData

__all__ = ["RAGPipeline"]


class RAGPipeline:
    """Sequential step runner."""

    def __init__(
        self, steps: list[Callable[[PipelineData], Awaitable[PipelineData]]]
    ) -> None:
        self.steps = list(steps)

    async def run(self, data: PipelineData) -> PipelineData:
        """Execute steps sequentially, passing PipelineData through."""
        for step in self.steps:
            data = await step(data)
        return data
