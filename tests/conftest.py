"""tests/conftest.py — Global test configuration."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

# ── Pytest markers ──


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "online: requires running server")
    config.addinivalue_line("markers", "slow: takes >1s")


# ── Core fixtures ──


@pytest.fixture
def mock_llm():
    """Given: LLM dependency is needed.
    When: test requests mock_llm.
    Then: deterministic mock with streaming and completion support is returned."""
    from ai_assistant.core.ports.llm import ILLM

    m = MagicMock(spec=ILLM)
    m.complete = AsyncMock(
        return_value=MagicMock(
            text="Mocked AI response",
            metadata={},
            tool_calls=[],
        )
    )

    async def _stream(
        messages: list[Any],
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
    from ai_assistant.core.ports.embedder import IEmbedder

    m = MagicMock(spec=IEmbedder)
    m.embed = AsyncMock(return_value=[[0.1] * 384])
    m.dimension = 384
    return m


@pytest.fixture
def mock_reranker():
    """Given: reranker dependency is needed.
    When: test requests mock_reranker.
    Then: transparent pass-through mock is returned."""
    from ai_assistant.core.ports.reranker import IReranker, RerankResult

    m = MagicMock(spec=IReranker)
    m.retrieval_multiplier = 1

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
    from ai_assistant.core.domain.configs import VectorStoreConfigData
    from ai_assistant.core.ports.vector_store import IVectorStore

    m = MagicMock(spec=IVectorStore)
    m.add = AsyncMock(return_value=None)
    m.search = AsyncMock(return_value=[])
    m.delete = AsyncMock(return_value=None)
    m.save = AsyncMock(return_value=None)
    m.load = AsyncMock(return_value=None)
    m.list_by_filter = AsyncMock(return_value=[])
    # Drift #146: lifespan's mirror backfill reads the inventory through
    # the port — name it explicitly (#140/#141 discipline).
    m.list_chunks = AsyncMock(return_value=[])
    m.list_namespaces = AsyncMock(return_value=["test_default"])
    m.max_chunks = 10000
    # Spec-mocks see class attributes only, while IVectorStore.config
    # is an instance attribute set in __init__ (read by the pre-flight
    # max_chunks check) — the fixture must provide it explicitly.
    m.config = VectorStoreConfigData(max_chunks=10000)
    return m


@pytest.fixture
def mock_storage():
    """Given: storage dependency is needed.
    When: test requests mock_storage.
    Then: mock with history tracking is returned."""
    from ai_assistant.core.ports.storage import IChatStorage

    m = MagicMock(spec=IChatStorage)
    m.get_history = AsyncMock(return_value=[])
    m.save_message = AsyncMock(return_value=None)
    m.save_exchange = AsyncMock(return_value=None)
    m.get = AsyncMock(return_value=None)
    m.set = AsyncMock(return_value=None)
    m.init_db = AsyncMock(return_value=None)
    return m


@pytest.fixture
def memory_vector_store(tmp_path):
    """Return a fresh MemoryVectorStore for RAG/indexing tests."""
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
    from ai_assistant.core.domain.configs import VectorStoreConfigData

    return MemoryVectorStore(
        VectorStoreConfigData(dim=384, index_path=str(tmp_path / "vs"))
    )


@pytest.fixture
def mock_chunker():
    """Given: chunker dependency is needed.
    When: test requests mock_chunker.
    Then: single-chunk mock is returned."""
    from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
    from ai_assistant.core.ports.chunker import IChunker

    m = MagicMock(spec=IChunker)
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


# ---------------------------------------------------------------------------
# Mock state helpers — centralized to avoid duplication and shadowing
# ---------------------------------------------------------------------------


# F821 false positive: the annotation resolves via the
# function-scoped import below and is never evaluated at runtime.
def build_mock_state() -> InitializedAppState:  # type: ignore[name-defined]  # noqa: F821
    """Build a fresh InitializedAppState with isolated defaults.
    Returns a real dataclass instance so that adding a new required field
    to InitializedAppState raises TypeError here immediately, rather than
    silently creating a MagicMock attribute that hides contract drift.
    """
    from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
    from ai_assistant.api.deps import InitializedAppState, RAGState
    from ai_assistant.core.config import AppConfig
    from ai_assistant.core.domain.configs import SamplingConfig, TokenizerConfigData
    from ai_assistant.core.domain.messages import AssistantMessage
    from ai_assistant.core.ports.reranker import RerankResult
    from ai_assistant.core.task_registry import TaskRegistry
    from ai_assistant.features.chat.manager import ChatManager
    from ai_assistant.features.rag.manager import RAGManager

    config = AppConfig()

    from ai_assistant.core.ports.chunker import IChunker
    from ai_assistant.core.ports.embedder import IEmbedder
    from ai_assistant.core.ports.llm import ILLM
    from ai_assistant.core.ports.reranker import IReranker
    from ai_assistant.core.ports.storage import IChatStorage
    from ai_assistant.core.ports.vector_store import IVectorStore

    llm = AsyncMock(spec=ILLM)
    embedder = AsyncMock(spec=IEmbedder)
    vector_store = AsyncMock(spec=IVectorStore)
    chunker = AsyncMock(spec=IChunker)
    storage = AsyncMock(spec=IChatStorage)
    storage.get_history = AsyncMock(return_value=[])
    storage.save_message = AsyncMock(return_value=None)
    storage.save_exchange = AsyncMock(return_value=None)
    reranker = AsyncMock(spec=IReranker)
    reranker.retrieval_multiplier = 1

    # ── RAG pipeline port defaults ──
    embedder.embed = AsyncMock(return_value=[[0.1] * 384])
    embedder.dimension = 384
    llm.complete = AsyncMock(return_value=AssistantMessage(text="", metadata={}))
    llm.get_context_limit = MagicMock(return_value=8192)

    def _stream(*args, **kwargs):
        async def _agen():
            yield ""

        return _agen()

    llm.stream = MagicMock(side_effect=_stream)

    async def _rerank(query, chunks, top_k=None):
        return [RerankResult(chunk=c, score=1.0) for c in chunks]

    reranker.rerank = AsyncMock(side_effect=_rerank)

    vector_store.index_path = config.vector_store.index_path
    vector_store.search = AsyncMock(return_value=[])
    vector_store.add = AsyncMock(return_value=None)
    vector_store.delete = AsyncMock(return_value=None)
    vector_store.list_namespaces = AsyncMock(return_value=[])
    vector_store.list_by_filter = AsyncMock(return_value=[])
    vector_store.list_chunks = AsyncMock(return_value=[])
    vector_store.save = AsyncMock(return_value=None)
    vector_store.load = AsyncMock(return_value=None)

    chat_manager = ChatManager(
        llm=llm,
        reranker=reranker,
        max_context_tokens=config.chat.max_context_tokens,
        embedder=embedder,
        vector_store=vector_store,
        namespaces=config.namespaces,
        prompt_version=config.rag.prompt_version,
        top_k=config.rag.top_k,
        token_margin_min=config.rag.token_margin_min,
        token_margin_pct=config.rag.token_margin_pct,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        system_message=config.llm.system_message,
        sampling=SamplingConfig(
            max_tokens=config.llm.max_tokens,
            temperature=config.llm.temperature,
            top_p=config.llm.top_p,
            stop_sequences=tuple(config.llm.stop_sequences),
        ),
        rag_steps=list(config.rag.steps),
        lexical_index=None,
        date_month_names=dict(config.rag.date_month_names),
        date_prepositions=list(config.rag.date_prepositions),
    )
    rag_manager = RAGManager(
        llm=llm,
        vector_store=vector_store,
        embedder=embedder,
        reranker=reranker,
        token_margin_min=config.rag.token_margin_min,
        token_margin_pct=config.rag.token_margin_pct,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        system_message=config.llm.system_message,
        sampling=SamplingConfig(
            max_tokens=config.llm.max_tokens,
            temperature=config.llm.temperature,
            top_p=config.llm.top_p,
            stop_sequences=tuple(config.llm.stop_sequences),
        ),
        rag_steps=list(config.rag.steps),
        lexical_index=None,
        date_month_names=dict(config.rag.date_month_names),
        date_prepositions=list(config.rag.date_prepositions),
    )

    return InitializedAppState(
        config=config,
        task_registry=TaskRegistry(),
        llm=llm,
        embedder=embedder,
        vector_store=vector_store,
        storage=storage,
        chunker=chunker,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        reranker=reranker,
        rag_state=RAGState(),
        chat_manager=chat_manager,
        rag_manager=rag_manager,
    )


@pytest.fixture
def mock_state():
    """Return a fresh mock InitializedAppState for each test.
    Delegates to build_mock_state() for centralized construction.
    """
    return build_mock_state()


@pytest.fixture
def make_mock_state():
    """Factory fixture — returns a function that creates fresh mock states.
    Use when a test needs multiple isolated states or when a fixture
    (e.g. client) mutates the state and downstream tests must not see
    the mutation.
    """

    def _factory():
        return build_mock_state()

    return _factory


@pytest.fixture
def isolated_app_state(tmp_path):
    """Return a mock InitializedAppState with isolated temp paths.
    Overrides config paths to use tmp_path so that tests do not pollute
    the project data/ directory or collide with each other.
    """
    state = build_mock_state()
    # Isolate paths to tmp_path for filesystem safety
    from ai_assistant.core.config import SourceConfig

    state.config.vector_store.index_path = str(tmp_path / "indices")
    state.config.rag.sources = [
        SourceConfig(namespace="default", path=str(tmp_path / "documents"))
    ]
    state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
    state.config.storage.db_path = str(tmp_path / "storage.db")
    return state


# _reset_rag_globals removed: globals were eliminated in drift #26.
# RAGState is per-instance; no sentinel needed.


# ---------------------------------------------------------------------------
# Path A: real-adapter state factory (init_adapters over mock providers)
# ---------------------------------------------------------------------------


# F821 false positive: the annotation resolves via the
# function-scoped import below and is never evaluated at runtime.
def make_app_config(root: Path) -> AppConfig:  # type: ignore[name-defined]  # noqa: F821
    """Return a fresh AppConfig with every section named explicitly.

    Mock providers only (offline, no network); all disk paths under
    root; char_fallback tokenizer (no downloaded tokenizer files in a
    clean environment). The section field set mirrors the proven-valid
    _make_minimal_config from test_api.py, with three deltas: reranker
    "null" (a registered name — "dummy" only works where create_adapter
    is patched), paths under root, explicit tokenizer section. Tests
    mutate the returned config directly for per-case overrides
    (existing idiom, see isolated_app_state).
    """
    from ai_assistant.core.config import AppConfig

    return AppConfig.model_validate(
        {
            "llm": {
                "provider": "mock",
                "max_tokens": 100,
                "temperature": 0.7,
                "timeout": 5.0,
                "stop_sequences": [],
            },
            "embedder": {"provider": "mock", "dim": 384, "timeout": 5.0},
            "vector_store": {
                "provider": "memory",
                "dim": 384,
                "metric": "l2",
                "index_path": str(root / "indices"),
            },
            "chunker": {"provider": "simple", "chunk_size": 512, "chunk_overlap": 50},
            "tokenizer": {"provider": "char_fallback"},
            "storage": {"provider": "sqlite", "db_path": str(root / "storage.db")},
            "reranker": {
                "provider": "null",
                "model": "test",
                "api_base": "http://test",
                "timeout": 5.0,
            },
            "rag": {
                "steps": ["embed_query", "retrieve", "build_context", "generate"],
                "prompt_version": "v1",
                "prompt_name": "rag_default",
                "top_k": 3,
                "default_namespace": "test",
            },
        }
    )


@pytest.fixture
async def real_state(tmp_path):
    """Path A: real init_adapters over mock providers, tmp_path-scoped.

    Wiring is inherited from deps.init_adapters wholesale — the drift
    #151 class (constructor kwargs silently absorbed by defaults) has
    no place to happen here: a new required kwarg either flows through
    or fails loudly. Teardown mirrors lifespan stage 3 (adapter
    shutdown, production order) with a hard timeout per call (§7).
    Stages 1-2 (index persist, background tasks) are absent by design:
    no tasks are spawned here, indices are throwaway tmp data. Shutdown
    failures are NOT swallowed: production degrades to keep the cleanup
    sequence alive, tests fail loud — a broken shutdown is a defect the
    suite must catch.
    """
    import asyncio

    from ai_assistant.api.deps import init_adapters
    from ai_assistant.core.constants import ADAPTER_SHUTDOWN_TIMEOUT

    state = await init_adapters(make_app_config(tmp_path))
    yield state
    for adapter in (
        state.lexical_index,
        state.llm,
        state.embedder,
        state.vector_store,
        state.storage,
        state.reranker,
        state.chunker,
        state.tokenizer,
    ):
        if adapter is not None:
            await asyncio.wait_for(
                adapter.shutdown(), timeout=ADAPTER_SHUTDOWN_TIMEOUT
            )


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


# F821 false positive: the annotation resolves via the
# function-scoped import below and is never evaluated at runtime.
def build_chunk(
    text: str,
    chunk_id: str = "c1",
    source: str = "doc1",
    index: int = 0,
    total_chunks: int = 1,
    embedding: list[float] | None = None,
    source_uri: str | None = None,
    original_path: str | None = None,
    last_modified: str | None = None,
) -> Chunk:  # type: ignore[name-defined]  # noqa: F821
    """Return a fresh Chunk in the canonical test form.

    The canonical shape is the base repeated across test_chat (~14
    sites): fixed id, [1.0, 0.0, 0.0] embedding, plain ChunkMetadata.
    Metadata variations (source_uri, original_path, last_modified) are
    pass-through parameters. Owner stop-signal: if this grows per-test
    kwargs, it is a third factory version — halt and reassess.
    """
    from ai_assistant.core.domain.documents import Chunk, ChunkMetadata

    return Chunk(
        id=chunk_id,
        text=text,
        embedding=[1.0, 0.0, 0.0] if embedding is None else embedding,
        metadata=ChunkMetadata(
            source=source,
            index=index,
            total_chunks=total_chunks,
            source_uri=source_uri,
            original_path=original_path,
            last_modified=last_modified,
        ),
    )


@pytest.fixture
def make_chunk():
    """Factory fixture — returns build_chunk (canonical test chunks)."""
    return build_chunk


# ---------------------------------------------------------------------------
# Path B: shell mannequin (lifespan unit tests patch init_adapters)
# ---------------------------------------------------------------------------


def build_shell_state(vector_store: MagicMock | None = None) -> MagicMock:
    """Family-C mannequin: lifespan unit tests patch init_adapters, so
    the state is the mock's return value — path A cannot reach here.

    Sets the standard fields only; whatever the test VERIFIES (shutdown
    trackers, save timeouts, hanging shutdowns) stays inline in the
    test body. vector_store: None = the dense default ("hybrid off"
    contract); pass a spec-mock with index_path / list_namespaces /
    save when the test exercises index load or save.
    """
    from ai_assistant.core.ports.chunker import IChunker
    from ai_assistant.core.ports.embedder import IEmbedder
    from ai_assistant.core.ports.llm import ILLM
    from ai_assistant.core.ports.reranker import IReranker
    from ai_assistant.core.ports.storage import IChatStorage

    state = MagicMock()
    state.task_registry = AsyncMock()
    state.tokenizer = AsyncMock()
    state.vector_store = vector_store
    state.lexical_index = None  # hybrid off: the default contract
    state.llm = MagicMock(spec=ILLM)
    state.embedder = MagicMock(spec=IEmbedder)
    state.storage = MagicMock(spec=IChatStorage)
    state.reranker = MagicMock(spec=IReranker)
    state.chunker = MagicMock(spec=IChunker)
    return state


@pytest.fixture
def make_shell_state():
    """Factory fixture — returns build_shell_state (family-C mannequins)."""
    return build_shell_state


# ---------------------------------------------------------------------------
# TestClient fixtures
# ---------------------------------------------------------------------------


def _build_chat_manager_mock() -> MagicMock:
    """Build a mock ChatManager for TestClient fixtures.
    ChatManager is no longer in AppState; it is created per-request via
    Depends. We patch the dependency function to return this mock.
    """
    from ai_assistant.core.domain.messages import AssistantMessage

    mgr = MagicMock()
    mgr.chat = AsyncMock(
        return_value=AssistantMessage(text="Hello!", metadata={"tokens": 2})
    )

    async def fake_stream(*args, **kwargs):
        yield "Hello"
        yield "!"

    mgr.stream_chat = fake_stream
    return mgr


def _build_test_client(
    state, raise_server_exceptions: bool = True, manager: MagicMock | None = None
) -> TestClient:
    """Build a TestClient with mock state, auth header, and ChatManager override.

    manager: None builds the default chat manager mock; pass a custom
    mock to inject behavior (error paths, metadata capture, streams).
    """
    from ai_assistant.api.security import set_api_key
    from ai_assistant.features.chat.handlers import get_chat_manager
    from ai_assistant.main import create_app

    set_api_key("test-e2e-key")
    app = create_app(state=state)
    chat_mgr_mock = _build_chat_manager_mock() if manager is None else manager
    app.dependency_overrides[get_chat_manager] = lambda: chat_mgr_mock
    return TestClient(
        app,
        raise_server_exceptions=raise_server_exceptions,
        headers={"Authorization": "Bearer test-e2e-key"},
    )


@pytest.fixture
def client(mock_state):
    """Return a TestClient with mock state and auth header.
    Uses the function-scoped mock_state fixture so that each test gets a
    fresh state and mutations inside the test body affect the same object
    that the app uses.
    """
    return _build_test_client(mock_state)


@pytest.fixture
def client_no_raise(mock_state):
    """Return a TestClient that returns HTTP errors instead of throwing exceptions.
    Use this fixture for tests that expect 500 status codes.
    """
    return _build_test_client(mock_state, raise_server_exceptions=False)


@pytest.fixture
def make_test_client():
    """Factory fixture — returns _build_test_client for custom-manager tests."""
    return _build_test_client


# ---------------------------------------------------------------------------
# Contract test fixtures: parametrized adapter factories
# ---------------------------------------------------------------------------


# Adding a new adapter? Just append to params — no new test code needed.


@pytest.fixture(params=["mock", "openai_compatible"])
def embedder_adapter(request):
    """Factory: yield concrete IEmbedder for parametrized contract tests."""
    from ai_assistant.adapters.embedder_mock import MockEmbedder
    from ai_assistant.adapters.embedder_openai_compatible import (
        OpenAICompatibleEmbedder,
    )
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
    from ai_assistant.core.domain.configs import VectorStoreConfigData

    if request.param == "memory":
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

        return MemoryVectorStore(
            VectorStoreConfigData(
                dim=384,
                index_path=str(tmp_path / "vs"),
            )
        )
    if request.param == "faiss":
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        return FaissVectorStore(
            VectorStoreConfigData(
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
        return NullReranker(RerankerConfigData(model="null", api_base="", api_key=""))
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
        return SimpleChunker(ChunkerConfigData(chunk_size=100, chunk_overlap=0))
    raise ValueError(f"Unknown chunker: {request.param}")


@pytest.fixture(params=["sqlite"])
def chat_storage_adapter(request):
    """Factory: yield concrete IChatStorage for parametrized contract tests."""
    from ai_assistant.adapters.storage_sqlite import SQLiteStorage
    from ai_assistant.core.domain.configs import StorageConfigData

    if request.param == "sqlite":
        return SQLiteStorage(StorageConfigData(db_path=":memory:"))
    raise ValueError(f"Unknown storage: {request.param}")
