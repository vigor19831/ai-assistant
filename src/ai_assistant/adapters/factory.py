"""Adapter factory — explicit registry lookup, no if/elif.

All adapter imports are eager at module load time so that @register
decorators populate the registry before create_adapter() is called.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from ai_assistant.adapters._registry import get_registry, register
from ai_assistant.adapters.char_fallback_tokenizer import (
    CharFallbackTokenizer,  # noqa: F401
)

# Eager imports to trigger @register side-effects.
# Each adapter module self-registers via @register on import.
from ai_assistant.adapters.chunker_simple import SimpleChunker  # noqa: F401
from ai_assistant.adapters.embedder_mock import MockEmbedder  # noqa: F401
from ai_assistant.adapters.embedder_openai_compatible import (  # noqa: F401
    OpenAICompatibleEmbedder,
)
from ai_assistant.adapters.llm_mock import MockLLM  # noqa: F401
from ai_assistant.adapters.llm_openai_compatible import (  # noqa: F401
    OpenAICompatibleLLM,
)
from ai_assistant.adapters.reranker_api import APIReranker  # noqa: F401
from ai_assistant.adapters.reranker_null import NullReranker  # noqa: F401
from ai_assistant.adapters.storage_sqlite import SQLiteStorage  # noqa: F401
from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer  # noqa: F401
from ai_assistant.adapters.vector_store_faiss import FaissVectorStore  # noqa: F401
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore  # noqa: F401

__all__ = ["create_adapter", "register"]


# Adapters that accept an external http_client
_HTTP_ADAPTERS: frozenset[tuple[str, str]] = frozenset({
    ("llm", "openai_compatible"),
    ("embedder", "openai_compatible"),
    ("reranker", "api"),
})


def create_adapter(
    port: str, name: str, config: Any, http_client: httpx.AsyncClient | None = None
) -> Any:
    """Create an adapter instance by port and name via registry lookup.

    Args:
        port: Port category (e.g., "llm", "embedder").
        name: Adapter identifier (e.g., "mock", "openai_compatible").
        config: Configuration object passed to adapter __init__.
        http_client: Shared httpx.AsyncClient for network adapters.
            Ignored for non-HTTP adapters (mock, memory, etc.).

    Returns:
        Adapter instance.

    Raises:
        ValueError: If port/name combination is not supported.
    """
    registry = get_registry()

    # -- Special-case: faiss import error --
    if port == "vector_store" and name == "faiss":
        try:
            import faiss  # noqa: F401
        except ImportError as exc:
            raise ValueError(
                "faiss-cpu is not installed but vector_store.provider='faiss'"
            ) from exc

    # -- Special-case: sqlite import error --
    if port == "storage" and name == "sqlite":
        try:
            import sqlite3  # noqa: F401
        except ImportError as exc:
            raise ValueError(
                "sqlite3 not available but storage.provider='sqlite'"
            ) from exc

    port_adapters = registry.get(port)
    if port_adapters is None:
        raise ValueError(f"Unknown adapter port '{port}'")

    cls = port_adapters.get(name)
    if cls is None:
        raise ValueError(f"No {port} adapter registered for '{name}'")

    if (port, name) in _HTTP_ADAPTERS and http_client is not None:
        return cls(config, http_client=http_client)
    return cls(config)
