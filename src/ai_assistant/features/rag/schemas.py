"""RAG feature Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "DeleteRequest",
    "DeleteResponse",
    "HealthResponse",
    "IndexRequest",
    "IndexResponse",
    "NamespaceListResponse",
    "QueryRequest",
    "QueryResponse",
    "RagMetrics",
    "ReindexRequest",
    "SaveChatRequest",
]

_NS_PATTERN = r"^[a-z][a-z0-9_-]*$"


def _reject_chat_ns(v: str | None) -> str | None:
    """Reject namespace values starting with 'chat_' (reserved prefix)."""
    if v is not None and v.startswith("chat_"):
        raise ValueError("namespace cannot start with 'chat_' (reserved)")
    return v


class IndexRequest(BaseModel):
    """Request to index documents."""

    documents: list[dict[str, Any]] = Field(
        ...,
        description="List of {id, content, metadata} objects",
    )
    namespace: str | None = Field(
        default=None,
        pattern=_NS_PATTERN,
        description="Index namespace",
    )

    @field_validator("namespace", mode="after")
    @classmethod
    def _reject_chat(cls, v: str | None) -> str | None:
        return _reject_chat_ns(v)


class IndexResponse(BaseModel):
    """Response after indexing."""

    indexed_count: int
    chunk_count: int
    namespace: str | None = None
    errors: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    """RAG query request."""

    query: str
    top_k: int | None = Field(default=None, ge=1, le=50)
    prompt_name: str | None = None
    prompt_version: str | None = None
    namespace: str | None = Field(
        default=None,
        pattern=_NS_PATTERN,
        description="Query namespace",
    )
    chat_history: list[tuple[str, str]] | None = Field(
        default=None, description="Previous messages for context"
    )

    @field_validator("namespace", mode="after")
    @classmethod
    def _reject_chat(cls, v: str | None) -> str | None:
        return _reject_chat_ns(v)

    @field_validator("chat_history")
    @classmethod
    def _validate_chat_history_roles(
        cls, v: list[tuple[str, str]] | None
    ) -> list[tuple[str, str]] | None:
        if v is None:
            return v
        for role, _text in v:
            if role not in ("user", "assistant"):
                raise ValueError(
                    f"chat_history role must be 'user' or 'assistant', got {role!r}"
                )
        return v


class RagMetrics(BaseModel):
    """Diagnostic snapshot of a single RAG query."""

    chunks_used: int
    rerank_scores: list[float]
    context_tokens: int
    prompt_name: str
    pipeline_errors: list[str]
    duration_ms: int


class QueryResponse(BaseModel):
    """RAG query response."""

    model_config = ConfigDict(extra="ignore")
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    chunks_used: int
    errors: list[str] = Field(default_factory=list)
    metrics: RagMetrics | None = None


class DeleteRequest(BaseModel):
    """Delete documents/chunks request."""

    document_ids: list[str] | None = None
    chunk_ids: list[str] | None = None
    namespace: str | None = Field(
        default=None,
        pattern=_NS_PATTERN,
        description="Target namespace",
    )
    clear: bool = Field(default=False, description="Clear all chunks in namespace")

    @field_validator("namespace", mode="after")
    @classmethod
    def _reject_chat(cls, v: str | None) -> str | None:
        return _reject_chat_ns(v)


class DeleteResponse(BaseModel):
    """Delete response."""

    deleted_chunks: int
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """RAG health check."""

    status: str
    index_loaded: bool
    chunk_count: int
    embedder_dim: int | None = None


class NamespaceListResponse(BaseModel):
    """Available RAG namespaces."""

    namespaces: list[str]


class SaveChatRequest(BaseModel):
    """Request to save chat content to documents folder."""

    content: str = Field(..., min_length=1, description="Chat content to save")
    namespace: str = Field(
        default="default",
        pattern=_NS_PATTERN,
        description="Target namespace",
    )
    filename: str = Field(
        default="chat.md",
        pattern=r"^[^./\\][^/\\]*$",
        description="Filename without path traversal",
    )

    @field_validator("namespace", mode="after")
    @classmethod
    def _reject_chat(cls, v: str) -> str:
        if v.startswith("chat_"):
            raise ValueError("namespace cannot start with 'chat_' (reserved)")
        return v


class ReindexRequest(BaseModel):
    """Request to reindex documents from namespaces."""

    target_namespace: str | None = Field(
        default=None,
        pattern=_NS_PATTERN,
        description="Specific namespace to reindex, or None for all.",
    )
    clear: bool = Field(
        default=False, description="If True, clear existing chunks before indexing."
    )

    @field_validator("target_namespace", mode="after")
    @classmethod
    def _reject_chat(cls, v: str | None) -> str | None:
        return _reject_chat_ns(v)
