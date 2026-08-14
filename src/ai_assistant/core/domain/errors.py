"""Domain exceptions."""

from __future__ import annotations

__all__ = [
    "EMBEDDER_NOT_PROVIDED",
    "INTERNAL_SERVER_ERROR",
    "LLM_NOT_PROVIDED",
    "LLM_UNAVAILABLE",
    "LLM_UNAVAILABLE_MSG",
    "QUERY_EMBEDDING_MISSING",
    "QUERY_MISSING",
    "QUERY_TEXT_MISSING",
    "VECTOR_STORE_NOT_PROVIDED",
    "AdapterError",
    "ConfigurationError",
    "VersionMismatchError",
]


class ConfigurationError(Exception):
    """Invalid configuration."""


class AdapterError(Exception):
    """Adapter operation failed."""


class VersionMismatchError(Exception):
    """Index/model version mismatch."""


# --- Pipeline step error messages ---
EMBEDDER_NOT_PROVIDED = "embed_query: embedder not provided"
QUERY_TEXT_MISSING = "embed_query: no query text"
VECTOR_STORE_NOT_PROVIDED = "retrieve: vector_store not provided"
QUERY_EMBEDDING_MISSING = "retrieve: no query embedding"
LLM_NOT_PROVIDED = "generate: llm not provided"
QUERY_MISSING = "generate: no query"
INTERNAL_SERVER_ERROR = "Internal server error"
LLM_UNAVAILABLE = "generate: LLM unavailable"
LLM_UNAVAILABLE_MSG = "LLM service temporarily unavailable. Please try again later."
RERANKER_NOT_PROVIDED = "rerank: reranker not provided"
