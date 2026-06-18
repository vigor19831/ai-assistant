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

    if getattr(prompts_module, "_render", None) is not None:
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
    from ai_assistant.api.deps import InitializedAppState, RAGState
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
    state.rag_state = RAGState()
    return state


@pytest.fixture
def make_mock_state():
    """Factory fixture — returns a function that creates fresh mock states.

    Use when a test needs multiple isolated states or when a fixture
    (e.g. client) mutates the state and downstream tests must not see
    the mutation.
    """
    from ai_assistant.api.deps import InitializedAppState, RAGState
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
        state.rag_state = RAGState()
        return state

    return _factory


@pytest.fixture(autouse=True)
def _reset_rag_globals():
    """Given: RAG handler globals may leak between tests.
    When: each test starts.
    Then: no-op — globals were removed, RAGState is per-instance.

    Kept as autouse sentinel to document the architectural change.
    """
    yield


# ---------------------------------------------------------------------------
# Contract test fixtures: parametrized adapter factories
# ---------------------------------------------------------------------------
# Adding a new adapter? Just append to params — no new test code needed.


@pytest.fixture(params=["mock", "openai_compatible"])
def embedder_adapter(request):
    """Factory: yield concrete IEmbedder for parametrized contract tests."""
    from ai_assistant.adapters.embedder_mock import MockEmbedder
    from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder
    from ai_assistant.core.domain.configs import EmbedderConfigData

    if request.param == "mock":
        return MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )
    if request.param == "openai_compatible":
        return OpenAICompatibleEmbedder(
            EmbedderConfigData(
                model="test", dim=384, api_base="http://localhost:9999/v1", api_key="x"
            )
        )
    raise ValueError(f"Unknown embedder: {request.param}")


@pytest.fixture(params=["mock", "openai_compatible"])
def llm_adapter(request):
    """Factory: yield concrete ILLM for parametrized contract tests."""
    from ai_assistant.adapters.llm_mock import MockLLM
    from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
    from ai_assistant.core.domain.configs import LLMConfigData

    if request.param == "mock":
        return MockLLM(
            LLMConfigData(
                model="mock",
                api_base="",
                api_key="",
                max_tokens=100,
                temperature=0.7,
            )
        )
    if request.param == "openai_compatible":
        return OpenAICompatibleLLM(
            LLMConfigData(
                model="test",
                api_base="http://localhost:9999/v1",
                api_key="x",
                max_tokens=100,
                temperature=0.7,
                timeout=1.0,
            )
        )
    raise ValueError(f"Unknown llm: {request.param}")


@pytest.fixture(params=["memory", "faiss"])
def vector_store_adapter(request, tmp_path):
    """Factory: yield concrete IVectorStore for parametrized contract tests."""
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
    from ai_assistant.core.domain.configs import VectorStoreConfigData

    if request.param == "memory":
        return MemoryVectorStore(
            VectorStoreConfigData(
                provider="memory",
                dim=384,
                index_path=str(tmp_path / "vs"),
            )
        )
    if request.param == "faiss":
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        return FaissVectorStore(
            VectorStoreConfigData(
                provider="faiss",
                dim=384,
                index_path=str(tmp_path / "vs_faiss"),
            )
        )
    raise ValueError(f"Unknown vector_store: {request.param}")


@pytest.fixture(params=["null", "api"])
def reranker_adapter(request):
    """Factory: yield concrete IReranker for parametrized contract tests."""
    from ai_assistant.adapters.reranker_null import NullReranker
    from ai_assistant.core.domain.configs import RerankerConfigData

    if request.param == "null":
        return NullReranker(
            RerankerConfigData(model="null", api_base="", api_key="")
        )
    if request.param == "api":
        from ai_assistant.adapters.reranker_api import APIReranker

        return APIReranker(
            RerankerConfigData(
                model="test", api_base="http://localhost:9999/v1", api_key="x"
            )
        )
    raise ValueError(f"Unknown reranker: {request.param}")


@pytest.fixture(params=["simple"])
def chunker_adapter(request):
    """Factory: yield concrete IChunker for parametrized contract tests."""
    from ai_assistant.adapters.chunker_simple import SimpleChunker
    from ai_assistant.core.domain.configs import ChunkerConfigData

    if request.param == "simple":
        return SimpleChunker(
            ChunkerConfigData(chunk_size=100, chunk_overlap=0)
        )
    raise ValueError(f"Unknown chunker: {request.param}")


@pytest.fixture(params=["sqlite"])
def chat_storage_adapter(request):
    """Factory: yield concrete IChatStorage for parametrized contract tests."""
    from ai_assistant.adapters.storage_sqlite import SQLiteStorage
    from ai_assistant.core.domain.configs import StorageConfigData

    if request.param == "sqlite":
        storage = SQLiteStorage(
            StorageConfigData(provider="sqlite", path=":memory:")
        )
        return storage
    raise ValueError(f"Unknown storage: {request.param}")
