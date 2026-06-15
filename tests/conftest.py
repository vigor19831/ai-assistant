"""tests/conftest.py — Global test configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Logging ──
logger = logging.getLogger(__name__)


# ── Test config path ──
TEST_CONFIG_PATH = str(Path(__file__).parent / "config.test.yaml")
os.environ.setdefault("AI_CONFIG_PATH", TEST_CONFIG_PATH)


# ── Pytest markers ──
def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "online: requires running server")
    config.addinivalue_line("markers", "slow: takes >1s")


# ── Core fixtures ──


@pytest.fixture(autouse=True)
def reset_prompt_cache():
    """Given: prompt cache may contain state from previous tests.
    When: test starts.
    Then: cache is cleared; restored after test."""
    from ai_assistant.core import prompts as prompts_module

    original_env = getattr(prompts_module, "_env_cache", None)
    prompts_module._env_cache = {}

    if hasattr(prompts_module, "_render"):
        prompts_module._render.cache_clear()

    yield

    if original_env is not None:
        prompts_module._env_cache = original_env
    else:
        prompts_module._env_cache = {}


@pytest.fixture(autouse=True)
def cleanup_test_artifacts():
    """Given: previous tests may have created artifacts.
    When: test finishes.
    Then: test DBs and indices are removed."""
    yield
    for path in [
        Path("./data/test_storage.db"),
        Path("./data/test_memory.db"),
        Path("./data/indices/test"),
    ]:
        if path.exists():
            try:
                if path.is_file():
                    path.unlink()
                else:
                    import shutil

                    shutil.rmtree(path)
            except PermissionError:
                logger.warning("Could not remove %s", path)


@pytest.fixture
def mock_llm():
    """Given: LLM dependency is needed.
    When: test requests mock_llm.
    Then: deterministic mock with streaming and completion support is returned."""
    m = MagicMock()
    m.complete = AsyncMock(
        return_value=MagicMock(
            text="Mocked AI response",
            metadata={},
            tool_calls=[],
        )
    )

    async def _stream(
        messages: list,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        for chunk in ["Mocked", " streaming", " response"]:
            yield chunk

    m.stream = _stream
    return m


@pytest.fixture
def mock_embedder():
    """Given: embedder dependency is needed.
    When: test requests mock_embedder.
    Then: deterministic 384-dim mock vectors are returned."""
    m = MagicMock()
    m.embed = AsyncMock(return_value=[[0.1] * 384])
    m.dimension = 384
    return m


@pytest.fixture
def mock_reranker():
    """Given: reranker dependency is needed.
    When: test requests mock_reranker.
    Then: transparent pass-through mock is returned."""
    from ai_assistant.core.ports.reranker import RerankResult

    m = MagicMock()

    async def _rerank(query, chunks, top_k=None):
        results = [RerankResult(chunk=c, score=1.0) for c in chunks]
        return results[:top_k] if top_k else results

    m.rerank = AsyncMock(side_effect=_rerank)
    return m


@pytest.fixture
def mock_vector_store():
    """Given: vector store dependency is needed.
    When: test requests mock_vector_store.
    Then: mock with namespace support is returned."""
    m = MagicMock()
    m.add = AsyncMock(return_value=None)
    m.search = AsyncMock(return_value=[])
    m.delete = AsyncMock(return_value=None)
    m.save = AsyncMock(return_value=None)
    m.load = AsyncMock(return_value=None)
    m.list_by_filter = AsyncMock(return_value=[])
    m.list_namespaces = AsyncMock(return_value=["test_default"])
    m.max_chunks = 10000
    m.relevance_threshold = 0.3
    return m


@pytest.fixture
def mock_storage():
    """Given: storage dependency is needed.
    When: test requests mock_storage.
    Then: mock with history tracking is returned."""
    m = MagicMock()
    m.get_history = AsyncMock(return_value=[])
    m.save_message = AsyncMock(return_value=None)
    m.get = AsyncMock(return_value=None)
    m.set = AsyncMock(return_value=None)
    m.init_db = AsyncMock(return_value=None)
    return m


@pytest.fixture
def mock_chunker():
    """Given: chunker dependency is needed.
    When: test requests mock_chunker.
    Then: single-chunk mock is returned."""
    from ai_assistant.core.domain.documents import Chunk, ChunkMetadata

    m = MagicMock()
    m.chunk = AsyncMock(
        return_value=[
            Chunk(
                id="chunk-1",
                text="mocked chunk text",
                metadata=ChunkMetadata(source="doc-1", index=0, total_chunks=1),
            )
        ]
    )
    return m



@pytest.fixture
def mock_state():
    """Return a fresh mock InitializedAppState for each test.

    Uses a real AppConfig for schema fields and AsyncMock for adapters.
    This avoids MagicMock(spec=AppConfig) which does not auto-create
    Pydantic fields reliably.
    """
    from ai_assistant.api.deps import InitializedAppState
    from ai_assistant.core.config import AppConfig

    config = AppConfig()  # real config with all defaults
    state = MagicMock(spec=InitializedAppState)
    state.config = config  # real AppConfig, not MagicMock(spec=AppConfig)
    # Adapter fields — AsyncMock for test isolation
    state.llm = AsyncMock()
    state.embedder = AsyncMock()
    state.vector_store = AsyncMock()
    state.chunker = AsyncMock()
    state.storage = AsyncMock()
    state.reranker = AsyncMock()
    state.chat_manager = AsyncMock()
    state.pipeline = MagicMock()
    state.limiter = MagicMock()
    return state


@pytest.fixture
def make_mock_state():
    """Factory fixture — returns a function that creates fresh mock states.

    Use when a test needs multiple isolated states or when a fixture
    (e.g. client) mutates the state and downstream tests must not see
    the mutation.
    """
    from ai_assistant.api.deps import InitializedAppState
    from ai_assistant.core.config import AppConfig

    def _factory():
        config = AppConfig()
        state = MagicMock(spec=InitializedAppState)
        state.config = config
        state.llm = AsyncMock()
        state.embedder = AsyncMock()
        state.vector_store = AsyncMock()
        state.chunker = AsyncMock()
        state.storage = AsyncMock()
        state.reranker = AsyncMock()
        state.chat_manager = AsyncMock()
        state.pipeline = MagicMock()
        state.limiter = MagicMock()
        return state

    return _factory


@pytest.fixture(autouse=True)
def _reset_rag_globals():
    """Given: RAG handler globals may leak between tests.
    When: each test starts.
    Then: _reindex_status, _reindex_tasks, _reindex_semaphore are reset.
    """
    from ai_assistant.features.rag import handlers as rag_handlers

    # Save originals
    original_status = dict(rag_handlers._reindex_status)
    original_tasks = dict(rag_handlers._reindex_tasks)
    original_sem = rag_handlers._reindex_semaphore

    yield

    # Restore after test
    rag_handlers._reindex_status.clear()
    rag_handlers._reindex_status.update(original_status)
    rag_handlers._reindex_tasks.clear()
    rag_handlers._reindex_tasks.update(original_tasks)
    rag_handlers._reindex_semaphore = original_sem
