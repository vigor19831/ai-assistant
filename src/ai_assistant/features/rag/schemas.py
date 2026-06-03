"""RAG feature Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "DeleteRequest",
    "DeleteResponse",
    "HealthResponse",
    "IndexRequest",
    "IndexResponse",
    "NamespaceListResponse",
    "QueryRequest",
    "QueryResponse",
    "SaveChatRequest",
]


class IndexRequest(BaseModel):
    """Request to index documents."""

    documents: list[dict[str, Any]] = Field(
        ...,
        description="List of {id, content, metadata} objects",
    )
    namespace: str | None = Field(
        default=None,
        description="Index namespace (default, personal, work, etc.)",
    )


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
    namespace: str | None = Field(default=None, description="Query namespace")


class QueryResponse(BaseModel):
    """RAG query response."""

    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    chunks_used: int
    errors: list[str] = Field(default_factory=list)


class DeleteRequest(BaseModel):
    """Delete documents/chunks request."""

    document_ids: list[str] | None = None
    chunk_ids: list[str] | None = None
    namespace: str | None = Field(default=None, description="Target namespace")


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
        default="personal",
        pattern=r"^[a-z]+$",
        description="Target namespace",
    )
    filename: str = Field(
        default="chat.md",
        pattern=r"^[^./\\][^/\\]*$",
        description="Filename without path traversal",
    )
