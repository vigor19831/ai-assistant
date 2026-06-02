import contextlib

__all__ = [
    "chunker_simple",
    "embedder_mock",
    "embedder_openai_compatible",
    "llm_mock",
    "llm_openai_compatible",
    "reranker_api",
    "reranker_dummy",
    "storage_sqlite",
    "tools_calculator",
    "transport_fastapi",
    "vector_store_faiss",
    "vector_store_memory",
]

from . import (
    chunker_simple,
    embedder_mock,
    embedder_openai_compatible,
    llm_mock,
    llm_openai_compatible,
    reranker_api,
    reranker_dummy,
    tools_calculator,
    transport_fastapi,
    vector_store_memory,
)

# Lazy imports — optional dependencies, fail gracefully if not installed

with contextlib.suppress(ImportError):
    from . import storage_sqlite  # noqa: F401

with contextlib.suppress(ImportError):
    from . import vector_store_faiss  # noqa: F401
