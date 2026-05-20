"""RAGPipeline executor — sacred, immutable."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.domain.pipeline import PipelineData


class RAGPipeline:
    """Sequential step runner."""

    def __init__(
        self, steps: list[Callable[[PipelineData], Awaitable[PipelineData]]]
    ) -> None:
        self.steps = steps

    async def run(self, data: PipelineData) -> PipelineData:
        """Execute steps sequentially, passing PipelineData through."""
        for step in self.steps:
            data = await step(data)
        return data
