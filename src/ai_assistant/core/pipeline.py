"""RAGPipeline executor — sacred, immutable."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

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

    async def run(
        self, data: PipelineData, metadata: dict[str, Any] | None = None
    ) -> PipelineData:
        """Execute steps sequentially, passing PipelineData through.

        Args:
            data: Initial pipeline data.
            metadata: Optional metadata dict merged into data.metadata.
                Used to inject dependencies (embedder, vector_store, etc.)
                without coupling steps to AppState.
        """
        if metadata:
            data = replace(data, metadata={**data.metadata, **metadata})
        for step in self.steps:
            data = await step(data)
        return data
