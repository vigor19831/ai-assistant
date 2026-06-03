"""tests/conftest.py"""

from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Optional hypothesis integration ──
try:
    from hypothesis import settings

    settings.register_profile("default", max_examples=100, deadline=5000)
    settings.load_profile("default")
except ModuleNotFoundError:
    pass  # hypothesis not installed, fuzz tests skipped gracefully

# ── Force test config BEFORE any project imports ──
TEST_CONFIG_PATH = str(Path(__file__).parent / "config.test.yaml")
os.environ["AI_CONFIG_PATH"] = TEST_CONFIG_PATH

"""Global test configuration — auto-detects server, provides shared fixtures.

Design principles:
- AUTO_DETECT_SERVER: checks if localhost:8000 is alive
- OFFLINE_MODE: all tests work without server (mocks, TestClient)
- ONLINE_MODE: when server detected, runs integration tests too
- All fixtures are deterministic and reusable
"""


# ── Auto-detect server ──
def _is_server_running(
    host: str = "127.0.0.1", port: int = 8000, timeout: float = 0.5
) -> bool:
    """Check if server is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


SERVER_AVAILABLE = _is_server_running()


# ── Pytest markers ──
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "online: requires running server")
    config.addinivalue_line("markers", "offline: works without server")
    config.addinivalue_line("markers", "slow: takes >1s")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-skip online tests if server not available."""
    if not SERVER_AVAILABLE:
        skip_online = pytest.mark.skip(
            reason="Server not available (run: python scripts/start.py)"
        )
        for item in items:
            if "online" in item.keywords:
                item.add_marker(skip_online)


# ── Core fixtures ──


@pytest.fixture(autouse=True)
def reset_prompt_cache():
    """Clear prompt Environment and render cache between tests."""
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
    """Remove test DBs and indices after tests."""
    yield
    for path in [
        "./data/test_storage.db",
        "./data/test_memory.db",
        "./data/indices/test",
    ]:
        p = Path(path)
        if p.exists():
            try:
                if p.is_file():
                    p.unlink()
                else:
                    import shutil

                    shutil.rmtree(p)
            except PermissionError:
                pass


@pytest.fixture(scope="session")
def event_loop():
    """Consistent event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Deterministic mock fixtures ──


@pytest.fixture
def mock_llm():
    """LLM mock with complete streaming and completion support."""
    m = MagicMock()
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
    """Embedder mock — deterministic 384-dim vectors."""
    m = MagicMock()
    m.embed = AsyncMock(return_value=[[0.1] * 384])
    m.dimension = 384
    return m


@pytest.fixture
def mock_reranker():
    """Reranker mock — transparent pass-through."""
    from ai_assistant.core.ports.reranker import RerankResult

    m = MagicMock()

    async def _rerank(query, chunks, top_k=None):
        results = [RerankResult(chunk=c, score=1.0) for c in chunks]
        return results[:top_k] if top_k else results

    m.rerank = AsyncMock(side_effect=_rerank)
    return m


@pytest.fixture
def mock_vector_store():
    """Vector store mock with namespace support."""
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
    """Storage mock with history tracking."""
    m = MagicMock()
    m.get_history = AsyncMock(return_value=[])
    # Signature: get_history(conversation_id, limit=50, offset=0)
    m.save_message = AsyncMock(return_value=None)
    m.get = AsyncMock(return_value=None)
    m.set = AsyncMock(return_value=None)
    m.init_db = AsyncMock(return_value=None)
    return m


@pytest.fixture
def mock_chunker():
    """Chunker mock — single chunk output."""
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
def mock_state(
    mock_llm,
    mock_embedder,
    mock_vector_store,
    mock_storage,
    mock_reranker,
    mock_chunker,
):
    """Pre-built AppState with REAL instance for app.state compatibility."""
    from ai_assistant.api.deps import AppState
    from ai_assistant.core.config import load_config

    config = load_config(TEST_CONFIG_PATH)

    # Создаём реальный AppState, а не autospec — иначе hasattr/app.state ломается
    state = AppState(config=config)
    state.llm = mock_llm
    state.embedder = mock_embedder
    state.vector_store = mock_vector_store
    state.reranker = mock_reranker
    state.chunker = mock_chunker
    state.storage = mock_storage
    state.pipeline = MagicMock()
    state.pipeline.run = AsyncMock(
        return_value=MagicMock(
            chunks=[], response=MagicMock(text="RAG answer"), errors=[]
        )
    )
    # Removed: voice_recognizer, voice_synthesizer, vision, tool_registry, long_term_memory

    # AppState is mutable for test injection
    state.chat_manager = MagicMock()
    state.chat_manager.chat = AsyncMock(
        return_value=MagicMock(text="Mocked AI response", metadata={}, tool_calls=[])
    )

    async def _fake_stream(*args, **kwargs):
        for chunk in ["Mocked", " streaming", " response"]:
            yield chunk

    state.chat_manager.stream_chat = _fake_stream

    # DI-friendly: limiter for middleware
    state.limiter = MagicMock()
    state.limiter.is_allowed.return_value = True
    return state


@pytest.fixture
def client(mock_state, monkeypatch):
    """FastAPI TestClient with fully mocked state — 100% offline."""
    from fastapi.testclient import TestClient

    from ai_assistant.api.deps import get_state
    from ai_assistant.features.chat.manager import ChatManager
    from ai_assistant.main import create_app

    # Создаём реальный ChatManager с мокнутыми зависимостями
    # (нужен для тестов, которые подменяют stream_chat на async generator)
    chat_manager = ChatManager(
        llm=mock_state.llm,
        storage=mock_state.storage,
        history_limit=mock_state.config.chat.history_limit,
        max_context_tokens=mock_state.config.chat.max_context_tokens,
        tokenizer_model=mock_state.config.chat.tokenizer_model,
        embedder=mock_state.embedder,
        vector_store=mock_state.vector_store,
        reranker=mock_state.reranker,
    )
    mock_state.chat_manager = chat_manager

    # Отключаем проверку API key для тестов
    monkeypatch.setattr(
        "ai_assistant.api.security.get_expected_api_key", lambda: "test-key"
    )

    # Создаём свежий app для каждого теста — никаких хаков с глобальным app
    app = create_app(state=mock_state, lifespan=None)

    # Чистый DI: dependency override для endpoints, использующих Depends(get_state)
    app.dependency_overrides[get_state] = lambda: mock_state

    with TestClient(
        app,
        base_url="http://localhost",
        headers={"Authorization": "Bearer test-key"},
        raise_server_exceptions=True,
    ) as c:
        yield c


@pytest.fixture
def httpx_client():
    """Real HTTP client for online tests."""
    import httpx
    from ai_assistant.core.config import load_config

    # Authenticate against the real server using the same key it enforces.
    # Priority: env var > config.yaml (server config) > test config fallback.
    api_key = os.getenv("AI_API_KEY")
    if not api_key:
        cfg = load_config("config.yaml")
        api_key = cfg.security.api_key
    if not api_key:
        cfg = load_config(TEST_CONFIG_PATH)
        api_key = cfg.security.api_key
    api_key = api_key or "test-key"

### REPLACE
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    # Chat endpoints may need longer timeout for slow local LLMs
    timeout = httpx.Timeout(60.0, connect=10.0)
    with httpx.Client(
        base_url="http://127.0.0.1:8000", timeout=timeout, headers=headers
    ) as c:
        yield c


# ── Config fixtures for adapter tests ──


@pytest.fixture
def llm_cfg():
    """Minimal LLM config."""
    c = MagicMock()
    c.provider = "openai_compatible"
    c.api_base = os.getenv("AI_LLM_API_BASE", "http://127.0.0.1:8080/v1")
    c.max_tokens = 50
    c.temperature = 0.7
    c.timeout = 5.0
    c.stop_sequences = []
    return c


@pytest.fixture
def embedder_cfg():
    """Minimal embedder config."""
    c = MagicMock()
    c.provider = "mock"
    c.dim = 384
    c.timeout = 5.0
    return c


@pytest.fixture
def vs_cfg():
    """Minimal vector store config."""
    c = MagicMock()
    c.dim = 384
    c.metric = "l2"
    c.relevance_threshold = 0.3
    c.max_chunks = 10000
    return c


@pytest.fixture
def chunker_cfg():
    """Minimal chunker config."""
    c = MagicMock()
    c.chunk_size = 512
    c.chunk_overlap = 50
    return c
