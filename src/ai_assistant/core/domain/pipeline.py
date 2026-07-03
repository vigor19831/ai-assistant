"""Pipeline data carrier."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from .configs import RetryConfig

if TYPE_CHECKING:
    from .documents import Chunk
    from .messages import AssistantMessage, UserMessage
    from .ports.embedder import IEmbedder
    from .ports.llm import ILLM
    from .ports.reranker import IReranker
    from .ports.tokenizer import ITokenizer
    from .ports.vector_store import IVectorStore

__all__ = ["PipelineData", "PipelineConfig", "ReindexStatusEntry"]


@dataclass(frozen=True, slots=True)
class ReindexStatusEntry:
    """Immutable status entry for background reindex tasks.

    Replaces the untyped dict[str, object] bag in RAGState._status
    (DRIFT.md #14).
    """

    status: str
    started_at: float
    finished_at: float | None = None
    result: dict[str, object] | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Typed configuration for RAG pipeline steps.

    Mirrors a subset of RAGConfig as a stdlib dataclass
    so that pipeline steps have a typed contract without
    depending on Pydantic.
    """

    top_k: int = 5
    namespace: str = "default"
    relevance_threshold: float = 0.3
    prompt_name: str = "rag_strict"
    prompt_version: str = "v1"
    token_margin_min: int = 256
    token_margin_pct: float = 0.1
    retry: RetryConfig = field(default_factory=RetryConfig)

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {self.top_k}")

@dataclass(frozen=True, slots=True)
class PipelineData:
    query: UserMessage | None = None
    chunks: tuple[Chunk, ...] = field(default_factory=tuple)
    context: str = ""
    response: AssistantMessage | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)
    error_details: tuple[str | None, ...] = field(default_factory=tuple)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # Typed dependency fields — replace metadata bag
    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    reranker: IReranker | None = None
    llm: ILLM | None = None
    pipeline_config: PipelineConfig | None = None
    query_embedding: list[float] | None = None
    tokenizer: ITokenizer | None = None
    rerank_filtered_out: bool | None = None
    rerank_scores: list[float] | None = None

    def with_chunks(self, chunks: list[Chunk] | tuple[Chunk, ...]) -> PipelineData:
        """Return a new PipelineData with updated chunks."""
        return replace(self, chunks=tuple(chunks))

    def with_context(self, context: str) -> PipelineData:
        """Return a new PipelineData with updated context."""
        return replace(self, context=context)

    def with_response(self, response: AssistantMessage | None) -> PipelineData:
        """Return a new PipelineData with updated response."""
        return replace(self, response=response)

    def add_error(self, msg: str, detail: str | None = None) -> PipelineData:
        """Return a new PipelineData with an additional error message.

        Args:
            msg: User-facing error message (returned in API responses).
            detail: Internal diagnostic detail (for logs/debugging).
                If None, no detail is recorded for this error.
        """
        return replace(
            self,
            errors=(*self.errors, msg),
            error_details=(*self.error_details, detail),
        )

    def with_query_embedding(self, query_embedding: list[float] | None) -> PipelineData:
        """Return a new PipelineData with updated query_embedding."""
        return replace(self, query_embedding=query_embedding)

    def with_rerank_filtered_out(self, rerank_filtered_out: bool | None) -> PipelineData:
        """Return a new PipelineData with updated rerank_filtered_out."""
        return replace(self, rerank_filtered_out=rerank_filtered_out)

    def with_rerank_scores(self, rerank_scores: list[float] | None) -> PipelineData:
        """Return a new PipelineData with updated rerank_scores."""
        return replace(self, rerank_scores=rerank_scores)
