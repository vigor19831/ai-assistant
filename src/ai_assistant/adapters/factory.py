"""Adapter factory - explicit if/elif, no decorators, no side-effect imports.

All adapter imports happen INSIDE create_adapter() to support lazy loading.
This eliminates the need for eager @register side-effects in api/deps.py.
"""

from __future__ import annotations

from typing import Any

__all__ = ["create_adapter"]


def create_adapter(port: str, name: str, config: Any) -> Any:
    """Create an adapter instance by port and name.

    Args:
        port: Port category (e.g., "llm", "embedder").
        name: Adapter identifier (e.g., "mock", "openai_compatible").
        config: Configuration object passed to adapter __init__.

    Returns:
        Adapter instance.

    Raises:
        ValueError: If port/name combination is not supported.
    """
    # -- LLM --
    if port == "llm":
        if name == "mock":
            from ai_assistant.adapters.llm_mock import MockLLM

            return MockLLM(config)
        if name == "openai_compatible":
            from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM

            return OpenAICompatibleLLM(config)
        raise ValueError(f"No LLM adapter registered for '{name}'")

    # -- Embedder --
    if port == "embedder":
        if name == "mock":
            from ai_assistant.adapters.embedder_mock import MockEmbedder

            return MockEmbedder(config)
        if name == "openai_compatible":
            from ai_assistant.adapters.embedder_openai_compatible import (
                OpenAICompatibleEmbedder,
            )

            return OpenAICompatibleEmbedder(config)
        raise ValueError(f"No embedder adapter registered for '{name}'")

    # -- Vector Store --
    if port == "vector_store":
        if name == "memory":
            from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

            return MemoryVectorStore(config)
        if name == "faiss":
            try:
                from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
            except ImportError as exc:
                raise ValueError(
                    "faiss-cpu is not installed but vector_store.provider='faiss'"
                ) from exc
            return FaissVectorStore(config)
        raise ValueError(f"No vector_store adapter registered for '{name}'")

    # -- Chunker --
    if port == "chunker":
        if name == "simple":
            from ai_assistant.adapters.chunker_simple import SimpleChunker

            return SimpleChunker(config)
        raise ValueError(f"No chunker adapter registered for '{name}'")

    # -- Storage --
    if port == "storage":
        if name == "sqlite":
            try:
                from ai_assistant.adapters.storage_sqlite import SQLiteStorage
            except ImportError as exc:
                raise ValueError(
                    "sqlite3 not available but storage.provider='sqlite'"
                ) from exc
            return SQLiteStorage(config)
        raise ValueError(f"No storage adapter registered for '{name}'")

    # -- Reranker --
    if port == "reranker":
        if name == "api":
            from ai_assistant.adapters.reranker_api import APIReranker

            return APIReranker(config)
        if name == "null":
            from ai_assistant.adapters.reranker_null import NullReranker

            return NullReranker(config)
        raise ValueError(f"No reranker adapter registered for '{name}'")

    # Fallback for unknown port
    raise ValueError(f"Unknown adapter port '{port}'")
