"""RAGPipeline executor — sacred, immutable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_assistant.core.domain.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.pipeline import PipelineData


__all__ = ["RAGPipeline", "ConfigurationError"]


class RAGPipeline:
    """Sequential step runner."""

    def __init__(
        self, steps: list[Callable[[PipelineData], Awaitable[PipelineData]]]
    ) -> None:
        self.steps = list(steps)

    async def run(self, data: PipelineData) -> PipelineData:
        """Execute steps sequentially, passing PipelineData through.

        Args:
            data: Initial pipeline data with dependencies pre-populated
                via explicit typed fields (embedder, vector_store, etc.).

        Raises:
            ConfigurationError: If required fields are missing for
                the configured steps.
        """
        required_fields = self._required_fields_for_steps()
        missing = [f for f in required_fields if getattr(data, f) is None]
        if missing:
            raise ConfigurationError(
                f"Missing required PipelineData fields: {missing}"
            )
        for step in self.steps:
            data = await step(data)
        return data

    def _required_fields_for_steps(self) -> set[str]:
        """Return required PipelineData field names based on configured steps."""
        from ai_assistant.core.pipeline_steps import STEP_REGISTRY

        field_map: dict[str, set[str]] = {
            "embed_query": {"embedder"},
            "retrieve": {"vector_store"},
            "rerank": {"reranker"},
            "build_context": set(),
            "generate": {"llm", "pipeline_config"},
            "hyde_query": {"embedder", "llm"},
        }
        required: set[str] = set()
        for step_name, step_func in STEP_REGISTRY.items():
            if any(s is step_func for s in self.steps):
                required |= field_map.get(step_name, set())
        return required
