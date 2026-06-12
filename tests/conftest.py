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
    """Return a mock InitializedAppState for API/E2E tests."""
    from ai_assistant.api.deps import InitializedAppState
    from ai_assistant.core.config import AppConfig

    state = MagicMock(spec=InitializedAppState)
    state.config = MagicMock(spec=AppConfig)
    state.config.llm = MagicMock()
    state.config.llm.model = "test-model"
    state.config.llm.provider = "test-provider"
    state.config.embedder = MagicMock()
    state.config.embedder.dim = 384
    state.config.vector_store = MagicMock()
    state.config.vector_store.dim = 384
    state.config.rag = MagicMock()
    state.config.rag.prompt_version = "v1"
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
