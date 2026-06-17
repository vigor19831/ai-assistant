"""RAGPipeline executor — sacred, immutable."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.pipeline import PipelineData


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Immutable per-query pipeline configuration."""

    top_k: int = 5
    namespace: str = "default"
    relevance_threshold: float = 0.3
    prompt_name: str = "rag_strict"
    prompt_version: str = "v1"
    token_margin_min: int = 256
    token_margin_pct: float = 0.1


class ConfigurationError(Exception):
    """Pipeline metadata missing required keys."""


__all__ = ["PipelineConfig", "RAGPipeline", "ConfigurationError"]


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

        Raises:
            ConfigurationError: If required metadata keys are missing for
                the configured steps.
        """
        if metadata:
            # Validate required keys once at entry, not in each step
            required_keys = self._required_keys_for_steps()
            missing = [k for k in required_keys if k not in metadata]
            if missing:
                raise ConfigurationError(
                    f"Missing required metadata keys: {missing}"
                )
            data = replace(data, metadata={**data.metadata, **metadata})
        for step in self.steps:
            data = await step(data)
        return data

    def _required_keys_for_steps(self) -> set[str]:
        """Return required metadata keys based on configured steps."""
        from ai_assistant.core.pipeline_steps import STEP_REGISTRY

        key_map: dict[str, set[str]] = {
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
                required |= key_map.get(step_name, set())
        return required
