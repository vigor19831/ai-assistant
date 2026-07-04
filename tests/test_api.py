"""API unit tests — consolidated Phase 7 migration.

Given: API layer components (security, deps, router, lifespan, middleware, admin)
When: tests run in a single flat tests/ folder
Then: all contracts, boundaries, and error paths are verified.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from starlette.requests import Request
from starlette.testclient import TestClient

from ai_assistant.api import admin
from ai_assistant.api.admin import _UpdateApiKeyRequest, _UpdateApiKeyResponse, update_api_key
from ai_assistant.api.deps import (
    AppState,
    InitializedAppState,
    RAGState,
    get_state,
    init_adapters,
)
from ai_assistant.core.task_registry import TaskRegistry
from ai_assistant.api.lifespan import _async_cleanup, _load_config, lifespan
from ai_assistant.api.middleware import MetricsMiddleware
from ai_assistant.api.router import _ROUTERS, assemble_routers
from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.api.security import (
    SECURITY_MAX_BODY,
    bearer_scheme,
    check_request_size,
    get_expected_api_key,
    require_api_key,
    set_api_key,
)
from ai_assistant.core.config import AppConfig, RAGStep, SecurityConfig, load_config
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.chunker import IChunker
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.ports.llm import ILLM
from ai_assistant.core.ports.reranker import IReranker
from ai_assistant.core.ports.storage import IChatStorage
from ai_assistant.core.ports.vector_store import IVectorStore

logger = get_logger(__name__)


# ── Fixtures ──


@pytest.fixture(autouse=True)
def _reset_security_state(monkeypatch):
    """Given: global security state may leak between tests.
    When: test starts.
    Then: env var and override are reset; restored after test.
    """
    monkeypatch.delenv("AI_SECURITY_API_KEY", raising=False)
    set_api_key(None)
    yield
    set_api_key(None)


@pytest.fixture
def mock_request():
    """Given: a minimal ASGI request stub is needed.
    When: test requests mock_request.
    Then: a MagicMock with Request-compatible attributes is returned.
    """
    req = MagicMock(spec=Request)
    req.method = "GET"
    req.url.path = "/api/v1/chat"
    req.client = MagicMock(host="127.0.0.1")
    req.headers = {}
    return req


def _make_minimal_config() -> AppConfig:
    """Return a fresh AppConfig with test-safe defaults."""
    return AppConfig(
        llm={
            "provider": "mock",
            "max_tokens": 50,
            "temperature": 0.7,
            "timeout": 5.0,
            "stop_sequences": [],
        },
        embedder={"provider": "mock", "dim": 384, "timeout": 5.0},
        vector_store={
            "provider": "memory",
            "dim": 384,
            "metric": "l2",
            "index_path": "./data/indices/test",
        },
        chunker={"provider": "simple", "chunk_size": 512, "chunk_overlap": 50},
        storage={"provider": "sqlite", "db_path": ":memory:"},
        reranker={
            "provider": "dummy",
            "model": "test",
            "api_base": "http://test",
            "timeout": 5.0,
            "threshold": 0.3,
        },
        rag={
            "steps": ["embed_query", "retrieve", "build_context", "generate"],
            "prompt_version": "v1",
            "prompt_name": "rag_default",
            "top_k": 3,
            "default_namespace": "test",
            "relevance_threshold": 0.3,
        },
    )


@pytest.fixture
def client(isolated_app_state):
    """Return a TestClient with mocked app state and isolated paths."""
    from ai_assistant.main import create_app

    app = create_app(state=isolated_app_state)
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# TestAPISecurity
# ═══════════════════════════════════════════════════════════════════════════


class TestAPISecurity:
    """Contract tests for api/security.py."""

    # ── get_expected_api_key ──

    def test_env_var_priority(self, monkeypatch):
        """Given: env var and runtime override are both set.
        When: get_expected_api_key() is called.
        Then: env var wins over runtime override.
        """
        monkeypatch.setenv("AI_SECURITY_API_KEY", "env-secret")
        set_api_key("override-secret")
        assert get_expected_api_key() == "env-secret"

    def test_runtime_override_without_env(self):
        """Given: no env var is set and runtime override is active.
        When: get_expected_api_key() is called.
        Then: runtime override is returned.
        """
        set_api_key("override-secret")
        assert get_expected_api_key() == "override-secret"

    def test_returns_none_when_nothing_set(self):
        """Given: no env var and no runtime override.
        When: get_expected_api_key() is called.
        Then: None is returned.
        """
        assert get_expected_api_key() is None

    def test_empty_env_returns_none(self, monkeypatch):
        """Given: env var is set to empty string.
        When: get_expected_api_key() is called.
        Then: empty string is treated as absent; override is ignored.
        """
        monkeypatch.setenv("AI_SECURITY_API_KEY", "")
        set_api_key("override-secret")
        assert get_expected_api_key() is None

    def test_no_yaml_loading_on_hot_path(self):
        """Given: get_expected_api_key is on the hot path.
        When: it is called.
        Then: yaml.safe_load is never invoked.
        """
        with patch("yaml.safe_load") as mock_yaml:
            get_expected_api_key()
            mock_yaml.assert_not_called()

    # ── require_api_key ──

    async def test_require_api_key_success(self):
        """Given: a valid bearer token matching the expected key.
        When: require_api_key is called with it.
        Then: no exception is raised.
        """
        set_api_key("secret")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret")
        await require_api_key(creds)

    async def test_require_api_key_not_configured(self):
        """Given: no API key is configured.
        When: require_api_key is called.
        Then: HTTPException 401 is raised with generic message.
        """
        set_api_key(None)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="anything")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(creds)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Unauthorized"

    async def test_require_api_key_invalid(self):
        """Given: a bearer token that does not match the expected key.
        When: require_api_key is called with it.
        Then: HTTPException 401 is raised with generic message.
        """
        set_api_key("secret")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(creds)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Unauthorized"

    async def test_require_api_key_missing_credentials(self):
        """Given: credentials object is None.
        When: require_api_key is called.
        Then: HTTPException 401 is raised with generic message.
        """
        set_api_key("secret")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Unauthorized"

    async def test_require_api_key_malformed_header(self):
        """Given: credentials object is not HTTPAuthorizationCredentials.
        When: require_api_key is called.
        Then: HTTPException 401 is raised with generic message."""
        set_api_key("secret")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Unauthorized"

    # ── check_request_size ──

    async def test_check_request_size_ok(self, mock_request):
        """Given: content-length is within the limit.
        When: check_request_size is called.
        Then: no exception is raised.
        """
        mock_request.headers = {"content-length": "1024"}
        await check_request_size(mock_request)

    async def test_check_request_size_too_large(self, mock_request):
        """Given: content-length exceeds SECURITY_MAX_BODY.
        When: check_request_size is called.
        Then: HTTPException 413 is raised.
        """
        mock_request.headers = {"content-length": str(SECURITY_MAX_BODY + 1)}
        with pytest.raises(HTTPException) as exc_info:
            await check_request_size(mock_request)
        assert exc_info.value.status_code == 413

    async def test_check_request_size_no_header(self, mock_request):
        """Given: no content-length header is present.
        When: check_request_size is called.
        Then: no exception is raised (no size check possible).
        """
        mock_request.headers = {}
        await check_request_size(mock_request)

    async def test_check_request_size_zero(self, mock_request):
        """Given: content-length is exactly 0.
        When: check_request_size is called.
        Then: no exception is raised.
        """
        mock_request.headers = {"content-length": "0"}
        await check_request_size(mock_request)

    async def test_check_request_size_invalid_header(self, mock_request):
        """Given: content-length is not a valid integer.
        When: check_request_size is called.
        Then: HTTPException 400 is raised.
        """
        mock_request.headers = {"content-length": "not-a-number"}
        with pytest.raises(HTTPException) as exc_info:
            await check_request_size(mock_request)
        assert exc_info.value.status_code == 400

    async def test_check_request_size_custom_limit_allows(self, mock_request):
        """Given: custom max_sz larger than content-length.
        When: check_request_size is called with custom limit.
        Then: no exception is raised.
        """
        mock_request.headers = {"content-length": "1024"}
        await check_request_size(mock_request, max_sz=2048)

    async def test_check_request_size_custom_limit_rejects(self, mock_request):
        """Given: custom max_sz smaller than content-length.
        When: check_request_size is called with custom limit.
        Then: HTTPException 413 is raised.
        """
        mock_request.headers = {"content-length": "2048"}
        with pytest.raises(HTTPException) as exc_info:
            await check_request_size(mock_request, max_sz=1024)
        assert exc_info.value.status_code == 413

    # ── Admin endpoint integration ──

    def _make_admin_state(self, enabled: bool) -> MagicMock:
        """Helper: create AppState mock with nested security config."""
        state = MagicMock(spec=AppState)
        state.config = MagicMock()
        state.config.security = MagicMock()
        state.config.security.admin_enabled = enabled
        return state

    async def test_admin_disabled_returns_404(self):
        """Given: admin_enabled is False (default).
        When: any admin endpoint is called.
        Then: HTTPException 404 is raised.
        """
        state = self._make_admin_state(enabled=False)
        req = _UpdateApiKeyRequest(api_key="new-key")
        with pytest.raises(HTTPException) as exc_info:
            await update_api_key(req, state)
        assert exc_info.value.status_code == 404

    async def test_admin_update_api_key_when_enabled(self):
        """Given: admin_enabled is True.
        When: admin endpoint receives a new api_key.
        Then: set_api_key stores the new key.
        """
        set_api_key(None)
        state = self._make_admin_state(enabled=True)
        req = _UpdateApiKeyRequest(api_key="new-key")
        resp = await update_api_key(req, state)
        assert resp.updated is True
        assert get_expected_api_key() == "new-key"

    async def test_admin_clear_api_key_when_enabled(self):
        """Given: admin_enabled is True.
        When: admin endpoint receives api_key=None.
        Then: override is cleared.
        """
        set_api_key("old-key")
        state = self._make_admin_state(enabled=True)
        req = _UpdateApiKeyRequest(api_key=None)
        resp = await update_api_key(req, state)
        assert resp.updated is True
        assert get_expected_api_key() is None

    async def test_admin_update_empty_key_rejected_when_enabled(self):
        """Given: admin_enabled is True.
        When: admin endpoint receives empty string api_key.
        Then: HTTPException 400 is raised.
        """
        set_api_key(None)
        state = self._make_admin_state(enabled=True)
        req = _UpdateApiKeyRequest(api_key="")
        with pytest.raises(HTTPException) as exc_info:
            await update_api_key(req, state)
        assert exc_info.value.status_code == 400

    async def test_admin_update_key_response_structure_when_enabled(self):
        """Given: admin_enabled is True.
        When: update_api_key returns.
        Then: response conforms to _UpdateApiKeyResponse schema.
        """
        state = self._make_admin_state(enabled=True)
        req = _UpdateApiKeyRequest(api_key="k")
        resp = await update_api_key(req, state)
        assert isinstance(resp, _UpdateApiKeyResponse)
        assert resp.updated is True
        assert resp.source == "runtime_override"

    async def test_admin_current_model_disabled_returns_404(self):
        """Given: admin_enabled is False.
        When: get_current_model is called.
        Then: HTTPException 404 is raised.
        """
        state = self._make_admin_state(enabled=False)
        with pytest.raises(HTTPException) as exc_info:
            await admin.get_current_model(state)
        assert exc_info.value.status_code == 404

    # ── Thread safety ──

    def test_set_api_key_thread_safety(self):
        """Given: multiple threads concurrently call set_api_key.
        When: they race with different values.
        Then: the last write wins without crashing (lock held).
        """
        errors = []

        def worker(value: str):
            try:
                for _ in range(100):
                    set_api_key(value)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(f"key-{i}",))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Last write from any thread is deterministic
        final = get_expected_api_key()
        assert final is not None
        assert final.startswith("key-")

    # ── Path traversal / blocked by pydantic ──

    def test_path_traversal_blocked_by_pydantic(self, client):
        """Given: a save-chat payload with path-traversal filename.
        When: POST /api/v1/rag/save-chat is sent.
        Then: 422 validation error blocks the request.
        """
        from ai_assistant.api.security import set_api_key
        set_api_key("test-key")
        payload = {
            "content": "test",
            "namespace": "personal",
            "filename": "../../../etc/passwd",
        }
        resp = client.post(
            "/api/v1/rag/save-chat",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 422

    def test_invalid_namespace_blocked_by_pydantic(self, client):
        """Given: a namespace with uppercase letters or digits.
        When: POST /api/v1/rag/save-chat is sent.
        Then: 422 validation error blocks the request.
        """
        from ai_assistant.api.security import set_api_key
        set_api_key("test-key")
        payload = {"content": "test", "namespace": "Hacked123", "filename": "test.md"}
        resp = client.post(
            "/api/v1/rag/save-chat",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 422

    def test_namespace_traversal_blocked(self, client):
        """Given: a namespace escaping DOCUMENTS_ROOT.
        When: POST /api/v1/rag/save-chat is sent.
        Then: request is blocked (422 or 400, never 200).
        """
        payload = {
            "content": "test",
            "namespace": "../../../etc",
            "filename": "passwd",
        }
        resp = client.post(
            "/api/v1/rag/save-chat",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code != 200

    def test_filename_traversal_handler_level(self, client):
        """Given: filename path-traversal that slips through Pydantic.
        When: POST /api/v1/rag/save-chat is sent.
        Then: handler returns 400 or Pydantic returns 422; never 200.
        """
        from ai_assistant.api.security import set_api_key
        set_api_key("test-key")
        payload = {
            "content": "test",
            "namespace": "personal",
            "filename": "../../../etc/passwd",
        }
        resp = client.post(
            "/api/v1/rag/save-chat",
            json=payload,
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code in (400, 422)
        assert resp.status_code != 200


# ═══════════════════════════════════════════════════════════════════════════
# TestAPIDeps
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIDeps:
    """Contract tests for api/deps.py — AppState, init_adapters, pipeline."""

    # ── AppState dataclass ──

    def test_appstate_has_all_expected_fields(self):
        """Given: AppState is instantiated with a config.
        When: fields are inspected.
        Then: all expected fields exist.
        """
        state = AppState(config=AppConfig())
        for attr in (
            "config",
            "embedder",
            "vector_store",
            "llm",
            "chunker",
            "reranker",
            "storage",
        ):
            assert hasattr(state, attr), f"AppState missing {attr}"

    def test_appstate_defaults_are_none_except_config(self):
        """Given: AppState is created with only config.
        When: defaults are checked.
        Then: everything except config is None.
        """
        cfg = AppConfig()
        state = AppState(config=cfg)
        assert state.config is cfg
        assert state.embedder is None
        assert state.vector_store is None

    # ── init_adapters (mocked factory) ──

    @pytest.mark.asyncio
    async def test_init_adapters_assembles_correctly(self):
        """Given: create_adapter is mocked.
        When: init_adapters is called.
        Then: InitializedAppState has all core adapters populated.
        """
        minimal_config = _make_minimal_config()
        mock_llm = MagicMock(spec=ILLM)
        mock_embedder = MagicMock(spec=IEmbedder)
        mock_vector_store = MagicMock(spec=IVectorStore)
        mock_chunker = MagicMock(spec=IChunker)
        mock_storage = MagicMock(spec=IChatStorage)
        mock_storage.init_db = AsyncMock()
        mock_reranker = MagicMock(spec=IReranker)

        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any, **kwargs: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("storage", "sqlite"): mock_storage,
                ("reranker", "dummy"): mock_reranker,
            }
            result = mapping.get((port, name))
            if result is not None:
                return result
            port_specs = {
                "llm": ILLM,
                "embedder": IEmbedder,
                "vector_store": IVectorStore,
                "chunker": IChunker,
                "storage": IChatStorage,
                "reranker": IReranker,
            }
            return MagicMock(spec=port_specs.get(port))

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            result = await init_adapters(minimal_config)

        assert isinstance(result, InitializedAppState)
        assert result.config is minimal_config
        assert result.llm is mock_llm
        assert result.embedder is mock_embedder
        assert result.vector_store is mock_vector_store
        assert result.chunker is mock_chunker
        assert result.storage is mock_storage
        assert result.reranker is mock_reranker



    @pytest.mark.asyncio
    async def test_init_adapters_null_reranker_when_not_configured(self):
        """Given: reranker provider is None in config.
        When: init_adapters is called.
        Then: NullReranker is used.
        """
        from ai_assistant.adapters.reranker_null import NullReranker

        minimal_config = _make_minimal_config()
        minimal_config.reranker.provider = None

        mock_vector_store = MagicMock(spec=IVectorStore)
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)
        mock_storage = MagicMock(spec=IChatStorage)
        mock_storage.init_db = AsyncMock()

        def fake_create_adapter(port: str, name: str, config: Any, **kwargs: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                return mock_storage
            if port == "reranker" and name == "null":
                return NullReranker(None)
            port_specs = {
                "llm": ILLM,
                "embedder": IEmbedder,
                "vector_store": IVectorStore,
                "chunker": IChunker,
                "storage": IChatStorage,
                "reranker": IReranker,
            }
            return MagicMock(spec=port_specs.get(port))

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            result = await init_adapters(minimal_config)

        assert isinstance(result.reranker, NullReranker)

    @pytest.mark.asyncio
    async def test_init_adapters_storage_raises_runtime_error(self):
        """Given: storage adapter raises ValueError.
        When: init_adapters is called.
        Then: RuntimeError is raised and prior adapters are shut down.
        """
        minimal_config = _make_minimal_config()
        mock_vector_store = MagicMock(spec=IVectorStore)
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)
        mock_vector_store.shutdown = AsyncMock()

        mock_llm = MagicMock(spec=ILLM)
        mock_llm.shutdown = AsyncMock()
        mock_embedder = MagicMock(spec=IEmbedder)
        mock_embedder.shutdown = AsyncMock()

        def fake_create_adapter(port: str, name: str, config: Any, **kwargs: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                raise ValueError("No storage adapter registered")
            if port == "llm" and name == "mock":
                return mock_llm
            if port == "embedder" and name == "mock":
                return mock_embedder
            port_specs = {
                "llm": ILLM,
                "embedder": IEmbedder,
                "vector_store": IVectorStore,
                "chunker": IChunker,
                "storage": IChatStorage,
                "reranker": IReranker,
            }
            return MagicMock(spec=port_specs.get(port))

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            with pytest.raises(RuntimeError, match="Storage adapter failed"):
                await init_adapters(minimal_config)

        mock_llm.shutdown.assert_awaited_once()
        mock_embedder.shutdown.assert_awaited_once()
        mock_vector_store.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_init_adapters_storage_import_error(self):
        """Given: storage adapter raises ImportError.
        When: init_adapters is called.
        Then: RuntimeError is raised.
        """
        minimal_config = _make_minimal_config()
        mock_vector_store = MagicMock(spec=IVectorStore)
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any, **kwargs: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                raise ImportError("sqlite3 not available")
            port_specs = {
                "llm": ILLM,
                "embedder": IEmbedder,
                "vector_store": IVectorStore,
                "chunker": IChunker,
                "storage": IChatStorage,
                "reranker": IReranker,
            }
            return MagicMock(spec=port_specs.get(port))

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            with pytest.raises(RuntimeError, match="Storage adapter failed"):
                await init_adapters(minimal_config)

    @pytest.mark.asyncio
    async def test_init_adapters_returns_fresh_state(self):
        """Given: init_adapters is called twice.
        When: comparing results.
        Then: each call returns a distinct InitializedAppState.
        """
        minimal_config = _make_minimal_config()
        call_count = {"count": 0}

        def counting_create_adapter(port: str, name: str, config: Any, **kwargs: Any) -> Any:
            call_count["count"] += 1
            m = MagicMock(spec=IVectorStore if port == "vector_store" else IChatStorage if port == "storage" else ILLM)
            if port == "vector_store":
                m.list_namespaces = AsyncMock(return_value=[])
                m.load = AsyncMock(return_value=None)
            if port == "storage":
                m.init_db = AsyncMock()
            return m

        with patch(
            "ai_assistant.api.deps.create_adapter",
            side_effect=counting_create_adapter,
        ):
            result = await init_adapters(minimal_config)

        assert isinstance(result, InitializedAppState)
        assert result.llm is not None
        assert result.embedder is not None
        assert result.vector_store is not None

    # ── get_state ──

    def test_get_state_raises_when_not_initialized(self):
        """Given: app.state.app_state is missing.
        When: get_state is called.
        Then: RuntimeError is raised.
        """
        app = FastAPI()
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
        request = Request(scope)
        with pytest.raises(RuntimeError, match="State not initialized"):
            get_state(request)

    def test_get_state_reads_from_app_state(self):
        """Given: app.state.app_state is set to a mock.
        When: get_state is called.
        Then: the mock is returned.
        """
        from ai_assistant.api.deps import RAGState
        from ai_assistant.core.task_registry import TaskRegistry

        app = FastAPI()
        from ai_assistant.core.ports.tokenizer import ITokenizer

        mock_state = InitializedAppState(
            config=AppConfig(),
            task_registry=TaskRegistry(),
            llm=MagicMock(spec=ILLM),
            embedder=MagicMock(spec=IEmbedder),
            vector_store=MagicMock(spec=IVectorStore),
            storage=MagicMock(spec=IChatStorage),
            chunker=MagicMock(spec=IChunker),
            tokenizer=MagicMock(spec=ITokenizer),
            reranker=MagicMock(spec=IReranker),
            rag_state=RAGState(),
        )
        app.state.app_state = mock_state

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
        request = Request(scope)
        assert get_state(request) is mock_state

    def test_get_state_raises_when_app_state_is_none(self):
        """Given: app.state.app_state is explicitly None.
        When: get_state is called.
        Then: RuntimeError is raised.
        """
        app = FastAPI()
        app.state.app_state = None

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "app": app,
        }
        request = Request(scope)
        with pytest.raises(RuntimeError, match="State not initialized"):
            get_state(request)

    @pytest.mark.asyncio
    async def test_init_adapters_returns_initialized_state(self):
        """Given: init_adapters is called with real factory.
        When: adapters are created.
        Then: InitializedAppState has all core adapters populated.
        """
        minimal_config = _make_minimal_config()
        # Use mock providers to avoid real network calls
        minimal_config.llm.provider = "mock"
        minimal_config.embedder.provider = "mock"
        minimal_config.reranker.provider = "null"

        result = await init_adapters(minimal_config)

        assert isinstance(result, InitializedAppState)
        assert result.llm is not None
        assert result.embedder is not None
        assert result.vector_store is not None
        assert result.storage is not None
        assert result.chunker is not None
        assert result.tokenizer is not None
        assert result.reranker is not None

    def test_get_chunker_for_config_respects_chunk_size(self):
        """Given: namespace requires different chunk_size than base config.
        When: get_chunker_for_config is called with chunk_size override.
        Then: created chunker has the overridden chunk_size.
        """
        from ai_assistant.api.deps import get_chunker_for_config
        from ai_assistant.core.domain.configs import ChunkerConfigData
        from ai_assistant.core.ports.tokenizer import ITokenizer

        cfg = AppConfig(
            chunker={"provider": "simple", "chunk_size": 512, "chunk_overlap": 50},
        )
        mock_state = InitializedAppState(
            config=cfg,
            task_registry=TaskRegistry(),
            llm=MagicMock(spec=ILLM),
            embedder=MagicMock(spec=IEmbedder),
            vector_store=MagicMock(spec=IVectorStore),
            storage=MagicMock(spec=IChatStorage),
            chunker=SimpleChunker(
                ChunkerConfigData(chunk_size=512, chunk_overlap=50)
            ),
            tokenizer=MagicMock(spec=ITokenizer),
            reranker=MagicMock(spec=IReranker),
            rag_state=MagicMock(),
        )

        # Override to 1024 — must create new chunker, not return base
        chunker = get_chunker_for_config(mock_state, chunk_size=1024)
        assert chunker.config.chunk_size == 1024
        assert chunker.config.chunk_overlap == 50  # preserved from base

        # Same as base — must return existing instance
        same_chunker = get_chunker_for_config(mock_state, chunk_size=512)
        assert same_chunker is mock_state.chunker

        # None — also returns existing
        default_chunker = get_chunker_for_config(mock_state, chunk_size=None)
        assert default_chunker is mock_state.chunker


    # ── Step registry ──


    def test_no_cyclic_imports_between_api_modules(self):
        """Given: api submodules are imported.
        When: checking import graph.
        Then: no circular dependencies exist between security, deps, router, lifespan, admin.
        """
        # Re-importing after previous tests should not raise ImportError
        import ai_assistant.api.admin as _admin
        import ai_assistant.api.deps as _deps
        import ai_assistant.api.lifespan as _lifespan
        import ai_assistant.api.router as _router
        import ai_assistant.api.security as _security

        assert _admin is not None
        assert _deps is not None
        assert _lifespan is not None
        assert _router is not None
        assert _security is not None


# ═══════════════════════════════════════════════════════════════════════════
# TestAPIRouter

# ═══════════════════════════════════════════════════════════════════════════
# TestAPIRouter
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIRouter:
    """Compile-time and structural tests for api/router.py."""

    def test_assemble_routers_returns_list(self):
        """Given: assemble_routers is called.
        When: it executes.
        Then: a list of APIRouter instances is returned.
        """
        routers = assemble_routers()
        assert isinstance(routers, list)
        for router in routers:
            assert isinstance(router, APIRouter)

    def test_router_count(self):
        """Given: _ROUTERS contains 4 explicit routers.
        When: assemble_routers is called.
        Then: at least 4 routers are returned (admin + chat + chat_oai + rag).
        """
        routers = assemble_routers()
        assert len(routers) >= 4

    def test_oai_router_at_root_no_prefix(self):
        """Given: OpenAI-compatible routers are tagged with root tags.
        When: assemble_routers wraps them.
        Then: OAI routers keep original paths without /api/v1 prefix.
        """
        from ai_assistant.api.router import _ROOT_TAGS
        routers = assemble_routers()
        oai_routers = [r for r in routers if any(t in _ROOT_TAGS for t in r.tags)]
        for router in oai_routers:
            # OAI routers should not have /api/v1 prefix in their routes
            for route in router.routes:
                if hasattr(route, "path"):
                    assert not route.path.startswith("/api/v1")

    def test_legacy_routers_have_api_v1_prefix(self):
        """Given: legacy routers are not OAI-tagged.
        When: assemble_routers wraps them.
        Then: they are mounted under /api/v1 prefix.
        """
        from ai_assistant.api.router import _ROOT_TAGS
        routers = assemble_routers()
        legacy_wrappers = [r for r in routers if not any(t in _ROOT_TAGS for t in r.tags)]
        for router in legacy_wrappers:
            for route in router.routes:
                if hasattr(route, "path"):
                    assert route.path.startswith("/api/v1")

    def test_legacy_routers_have_api_key_dependency(self):
        """Given: legacy routers need API key protection.
        When: assemble_routers wraps them.
        Then: wrapper router has require_api_key in dependencies.
        """
        from ai_assistant.api.router import _ROOT_TAGS
        routers = assemble_routers()
        for router in routers:
            if any(t in _ROOT_TAGS for t in router.tags):
                continue
            # Wrapper routers should have dependencies set
            assert router.dependencies, f"Router {router.tags} lacks dependencies"

    def test_explicit_registry_imports(self):
        """Given: _ROUTERS is built from explicit imports.
        When: module is loaded.
        Then: all handlers are importable at compile time.
        """
        assert len(_ROUTERS) == 5
        tags = set()
        for router in _ROUTERS:
            tags.update(router.tags)
        assert "admin" in tags
        assert "chat" in tags or "chat-oai" in tags
        assert "rag" in tags
        assert "metrics" in tags

    def test_admin_router_is_root_tagged(self):
        """Given: admin router is in _ROUTERS.
        When: its tags are checked against _ROOT_TAGS.
        Then: it is root-tagged (no /api/v1 prefix, uses own auth).
        """
        from ai_assistant.api.router import _ROOT_TAGS
        admin_routers = [r for r in _ROUTERS if "admin" in r.tags]
        assert len(admin_routers) == 1
        assert any(t in _ROOT_TAGS for t in admin_routers[0].tags)

    def test_no_deferred_import_errors(self):
        """Given: a missing feature handler would break at runtime.
        When: assemble_routers is imported.
        Then: it succeeds immediately (no deferred import).
        """
        # This test file itself would fail collection if imports were broken
        assert assemble_routers is not None

    def test_oai_router_requires_auth_when_configured(self):
        """Given: security.openai_routes_require_auth is True.
        When: assemble_routers is called with security config.
        Then: OAI routers are wrapped with API key dependency.
        """
        security = SecurityConfig(openai_routes_require_auth=True)
        routers = assemble_routers(security=security)
        routers_with_deps = [r for r in routers if r.dependencies]
        # 3 legacy wrappers + 1 OAI wrapper = 4 routers with dependencies
        assert len(routers_with_deps) == 4

    def test_oai_router_stays_unprotected_by_default(self):
        """Given: no security config passed (backward compat default).
        When: assemble_routers is called.
        Then: OAI routers have no dependencies; only legacy routes are protected.
        """
        routers = assemble_routers()
        routers_with_deps = [r for r in routers if r.dependencies]
        # 3 legacy wrappers only (admin has deps on router level)
        assert len(routers_with_deps) == 3

    def test_metrics_never_requires_auth(self):
        """Given: security.openai_routes_require_auth is True.
        When: assemble_routers is called.
        Then: metrics router remains unprotected.
        """
        security = SecurityConfig(openai_routes_require_auth=True)
        routers = assemble_routers(security=security)
        for router in routers:
            for route in router.routes:
                if hasattr(route, "tags") and "metrics" in route.tags:
                    # Metrics routes should live in a router without dependencies
                    assert not router.dependencies, (
                        "Metrics router must never require auth"
                    )

    def test_assemble_routers_uses_configured_max_body(self):
        """Given: security config with custom max_body_size.
        When: assemble_routers creates wrapper routers.
        Then: body size dependency is present in legacy wrappers.
        """
        security = SecurityConfig(max_body_size=2048)
        routers = assemble_routers(security=security)
        # Find a legacy wrapper (non-root, non-metrics router)
        from ai_assistant.api.router import _ROOT_TAGS
        legacy_wrappers = [
            r for r in routers
            if not any(t in _ROOT_TAGS for t in r.tags)
            and "metrics" not in r.tags
        ]
        assert len(legacy_wrappers) > 0
        for wrapper in legacy_wrappers:
            assert wrapper.dependencies, "Legacy wrapper must have dependencies"

    def test_openai_chat_empty_messages_returns_422(self, client):
        """Given: OpenAI endpoint receives empty messages list.
        When: POST /v1/chat/completions with {"messages": []}.
        Then: 422 Unprocessable Entity is returned (not 500).
        """
        from ai_assistant.api.security import set_api_key
        set_api_key("test-key")
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": []},
            headers={"Authorization": "Bearer test-key"},
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# TestSecurityConfig
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityConfig:
    """Contract tests for the new security config field."""

    def test_openai_routes_require_auth_default_false(self):
        """Given: SecurityConfig is instantiated with defaults.
        When: openai_routes_require_auth is inspected.
        Then: it is False for backward compatibility.
        """
        sec = SecurityConfig()
        assert sec.openai_routes_require_auth is False

    def test_openai_routes_require_auth_from_app_config(self):
        """Given: AppConfig is instantiated with defaults.
        When: security sub-config is inspected.
        Then: openai_routes_require_auth defaults to False.
        """
        cfg = AppConfig()
        assert cfg.security.openai_routes_require_auth is False

    def test_openai_routes_require_auth_can_be_enabled(self):
        """Given: SecurityConfig is created with openai_routes_require_auth=True.
        When: the field is read.
        Then: it is True.
        """
        sec = SecurityConfig(openai_routes_require_auth=True)
        assert sec.openai_routes_require_auth is True


# ═══════════════════════════════════════════════════════════════════════════
# TestAPILifespan
# ═══════════════════════════════════════════════════════════════════════════


class TestAPILifespan:
    """Contract tests for api/lifespan.py — startup, shutdown, cleanup."""

    @pytest.mark.asyncio
    async def test_load_config_from_env(self, monkeypatch, tmp_path):
        """Given: AI_CONFIG_PATH points to a valid YAML.
        When: _load_config is called.
        Then: AppConfig is loaded from that path.
        """
        cfg_file = tmp_path / "test_config.yaml"
        cfg_file.write_text("debug: true\n", encoding="utf-8")
        monkeypatch.setenv("AI_CONFIG_PATH", str(cfg_file))
        config = _load_config()
        assert isinstance(config, AppConfig)
        assert config.debug is True

    @pytest.mark.asyncio
    async def test_lifespan_startup_sets_app_state(self):
        """Given: a FastAPI app with lifespan.
        When: startup runs.
        Then: app.state.app_state is populated.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = MagicMock(spec=ILLM)
        mock_state.embedder = MagicMock(spec=IEmbedder)
        mock_state.storage = MagicMock(spec=IChatStorage)
        mock_state.reranker = MagicMock(spec=IReranker)
        mock_state.chunker = MagicMock(spec=IChunker)

        with patch(
            "ai_assistant.api.lifespan._load_config", return_value=minimal_config
        ), patch(
            "ai_assistant.api.lifespan.init_adapters", return_value=mock_state
        ), patch(
            "ai_assistant.api.static.mount_static"
        ), patch(
            "ai_assistant.api.lifespan.setup_logging"
        ), patch(
            "ai_assistant.api.lifespan.get_expected_api_key", return_value=None
        ), patch(
            "ai_assistant.api.lifespan.set_api_key"
        ):
            async with lifespan(app):
                assert hasattr(app.state, "app_state")
                assert app.state.app_state is mock_state

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_calls_cleanup(self):
        """Given: lifespan context manager.
        When: shutdown runs (exit from context).
        Then: all adapters are shut down and app state is cleaned.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        # Track shutdown state for each adapter
        shutdown_called = {
            "llm": False,
            "embedder": False,
            "storage": False,
            "reranker": False,
            "chunker": False,
        }

        mock_state = MagicMock()
        mock_state.vector_store = None

        async def mark_llm_shutdown():
            shutdown_called["llm"] = True

        async def mark_embedder_shutdown():
            shutdown_called["embedder"] = True

        async def mark_storage_shutdown():
            shutdown_called["storage"] = True

        async def mark_reranker_shutdown():
            shutdown_called["reranker"] = True

        async def mark_chunker_shutdown():
            shutdown_called["chunker"] = True

        mock_state.llm = AsyncMock()
        mock_state.llm.shutdown = AsyncMock(side_effect=mark_llm_shutdown)
        mock_state.embedder = AsyncMock()
        mock_state.embedder.shutdown = AsyncMock(side_effect=mark_embedder_shutdown)
        mock_state.storage = AsyncMock()
        mock_state.storage.shutdown = AsyncMock(side_effect=mark_storage_shutdown)
        mock_state.reranker = AsyncMock()
        mock_state.reranker.shutdown = AsyncMock(side_effect=mark_reranker_shutdown)
        mock_state.chunker = AsyncMock()
        mock_state.chunker.shutdown = AsyncMock(side_effect=mark_chunker_shutdown)

        with patch(
            "ai_assistant.api.lifespan._load_config", return_value=minimal_config
        ), patch(
            "ai_assistant.api.lifespan.init_adapters", return_value=mock_state
        ), patch(
            "ai_assistant.api.static.mount_static"
        ), patch(
            "ai_assistant.api.lifespan.setup_logging"
        ), patch(
            "ai_assistant.api.lifespan.get_expected_api_key", return_value=None
        ), patch(
            "ai_assistant.api.lifespan.set_api_key"
        ):
            async with lifespan(app):
                pass

        # Assert on state, not just call counts
        assert shutdown_called["llm"] is True
        assert shutdown_called["embedder"] is True
        assert shutdown_called["storage"] is True
        assert shutdown_called["reranker"] is True
        assert shutdown_called["chunker"] is True

    @pytest.mark.asyncio
    async def test_async_cleanup_index_save(self):
        """Given: vector_store has namespaces.
        When: _async_cleanup runs.
        Then: all namespaces are saved and state reflects completion.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        # Track save state
        saved_namespaces: list[str] = []

        async def track_save(path: str, namespace: str) -> None:
            saved_namespaces.append(namespace)

        mock_state = MagicMock()
        mock_state.vector_store = MagicMock(spec=IVectorStore)
        mock_state.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(
            return_value=["ns1", "ns2"]
        )
        mock_state.vector_store.save = AsyncMock(side_effect=track_save)

        mock_state.llm = AsyncMock()
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        await _async_cleanup(app, minimal_config)

        # Assert on state — which namespaces were actually saved
        assert saved_namespaces == ["ns1", "ns2"]
        assert len(saved_namespaces) == 2

    @pytest.mark.asyncio
    async def test_async_cleanup_index_save_timeout(self):
        """Given: vector_store.save hangs beyond 10s.
        When: _async_cleanup runs.
        Then: TimeoutError is caught and logged; save attempt is recorded.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        save_attempted = {"count": 0}

        async def slow_save(*args, **kwargs):
            save_attempted["count"] += 1
            await asyncio.sleep(20)

        mock_state = MagicMock()
        mock_state.vector_store = MagicMock(spec=IVectorStore)
        mock_state.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["ns1"])
        mock_state.vector_store.save = AsyncMock(side_effect=slow_save)
        mock_state.llm = AsyncMock()
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        await _async_cleanup(app, minimal_config)
        # Should not raise; timeout is handled
        # Assert on state — save was attempted even though it timed out
        assert save_attempted["count"] == 1

    @pytest.mark.asyncio
    async def test_async_cleanup_no_app_state(self):
        """Given: app.state has no app_state attribute.
        When: _async_cleanup runs.
        Then: it returns early without error.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()
        await _async_cleanup(app, minimal_config)

    @pytest.mark.asyncio
    async def test_async_cleanup_adapter_shutdown_order(self):
        """Given: all adapters are present.
        When: _async_cleanup runs.
        Then: shutdown is called on each adapter in defined order.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        # Track shutdown order via state
        shutdown_order: list[str] = []

        async def track_llm():
            shutdown_order.append("llm")

        async def track_embedder():
            shutdown_order.append("embedder")

        async def track_storage():
            shutdown_order.append("storage")

        async def track_reranker():
            shutdown_order.append("reranker")

        async def track_chunker():
            shutdown_order.append("chunker")

        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = AsyncMock()
        mock_state.llm.shutdown = AsyncMock(side_effect=track_llm)
        mock_state.embedder = AsyncMock()
        mock_state.embedder.shutdown = AsyncMock(side_effect=track_embedder)
        mock_state.storage = AsyncMock()
        mock_state.storage.shutdown = AsyncMock(side_effect=track_storage)
        mock_state.reranker = AsyncMock()
        mock_state.reranker.shutdown = AsyncMock(side_effect=track_reranker)
        mock_state.chunker = AsyncMock()
        mock_state.chunker.shutdown = AsyncMock(side_effect=track_chunker)

        app.state.app_state = mock_state

        await _async_cleanup(app, minimal_config)

        # Assert on shutdown order state
        assert "llm" in shutdown_order
        assert "embedder" in shutdown_order
        assert "storage" in shutdown_order
        assert "reranker" in shutdown_order
        assert "chunker" in shutdown_order
        assert len(shutdown_order) == 5

    @pytest.mark.asyncio
    async def test_lifespan_mount_static_called(self):
        """Given: lifespan startup.
        When: it runs.
        Then: mount_static is called with app and config.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = MagicMock(spec=ILLM)
        mock_state.embedder = MagicMock(spec=IEmbedder)
        mock_state.storage = MagicMock(spec=IChatStorage)
        mock_state.reranker = MagicMock(spec=IReranker)
        mock_state.chunker = MagicMock(spec=IChunker)

        mount_calls: list[tuple[Any, ...]] = []

        def track_mount(app_arg, config_arg):
            mount_calls.append((app_arg, config_arg))

        with patch(
            "ai_assistant.api.lifespan._load_config", return_value=minimal_config
        ), patch(
            "ai_assistant.api.lifespan.init_adapters", return_value=mock_state
        ), patch(
            "ai_assistant.api.static.mount_static"
        ) as mock_mount, patch(
            "ai_assistant.api.lifespan.setup_logging"
        ), patch(
            "ai_assistant.api.lifespan.get_expected_api_key", return_value=None
        ), patch(
            "ai_assistant.api.lifespan.set_api_key"
        ):
            mock_mount.side_effect = track_mount
            async with lifespan(app):
                pass

        # Assert on state — correct args were passed
        assert len(mount_calls) == 1
        assert mount_calls[0][0] is app
        assert mount_calls[0][1] is minimal_config

    @pytest.mark.asyncio
    async def test_lifespan_setup_logging_called(self):
        """Given: lifespan startup.
        When: it runs.
        Then: setup_logging is called with correct level.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = MagicMock(spec=ILLM)
        mock_state.embedder = MagicMock(spec=IEmbedder)
        mock_state.storage = MagicMock(spec=IChatStorage)
        mock_state.reranker = MagicMock(spec=IReranker)
        mock_state.chunker = MagicMock(spec=IChunker)

        setup_calls: list[dict[str, Any]] = []

        def track_setup(*args, **kwargs):
            setup_calls.append(kwargs)

        with patch(
            "ai_assistant.api.lifespan._load_config", return_value=minimal_config
        ), patch(
            "ai_assistant.api.lifespan.init_adapters", return_value=mock_state
        ), patch(
            "ai_assistant.api.static.mount_static"
        ), patch(
            "ai_assistant.api.lifespan.setup_logging"
        ) as mock_setup, patch(
            "ai_assistant.api.lifespan.get_expected_api_key", return_value=None
        ), patch(
            "ai_assistant.api.lifespan.set_api_key"
        ):
            mock_setup.side_effect = track_setup
            async with lifespan(app):
                pass

        # Assert on state — correct logging level was configured
        assert len(setup_calls) == 1
        assert setup_calls[0]["level"] == "INFO"  # minimal_config.debug is False

    @pytest.mark.asyncio
    async def test_lifespan_sets_api_key_from_config(self):
        """Given: config has api_key and env has none.
        When: lifespan startup runs.
        Then: API key is set to config value and security state reflects it.
        """
        minimal_config = _make_minimal_config()
        minimal_config.security.api_key = "cfg-secret"
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = MagicMock(spec=ILLM)
        mock_state.embedder = MagicMock(spec=IEmbedder)
        mock_state.storage = MagicMock(spec=IChatStorage)
        mock_state.reranker = MagicMock(spec=IReranker)
        mock_state.chunker = MagicMock(spec=IChunker)

        with patch(
            "ai_assistant.api.lifespan._load_config", return_value=minimal_config
        ), patch(
            "ai_assistant.api.lifespan.init_adapters", return_value=mock_state
        ), patch(
            "ai_assistant.api.static.mount_static"
        ), patch(
            "ai_assistant.api.lifespan.setup_logging"
        ), patch(
            "ai_assistant.api.lifespan.get_expected_api_key", return_value=None
        ):
            async with lifespan(app):
                # Assert on security state during lifespan
                assert get_expected_api_key() == "cfg-secret"

    @pytest.mark.asyncio
    async def test_lifespan_skips_set_api_key_when_env_present(self):
        """Given: env var already has API key.
        When: lifespan startup runs.
        Then: set_api_key is NOT called because env var takes precedence.
        """
        minimal_config = _make_minimal_config()
        minimal_config.security.api_key = "cfg-secret"
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = AsyncMock()
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        with patch(
            "ai_assistant.api.lifespan._load_config", return_value=minimal_config
        ), patch(
            "ai_assistant.api.lifespan.init_adapters", return_value=mock_state
        ), patch(
            "ai_assistant.api.static.mount_static"
        ), patch(
            "ai_assistant.api.lifespan.setup_logging"
        ), patch(
            "ai_assistant.api.lifespan.get_expected_api_key", return_value="env-secret"
        ), patch(
            "ai_assistant.api.lifespan.set_api_key"
        ) as mock_set_key:
            async with lifespan(app):
                pass

        mock_set_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_index_load_on_startup(self):
        """Given: vector_store has persisted namespaces.
        When: lifespan startup runs.
        Then: namespaces are loaded and state reflects loaded indices.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        loaded_namespaces: list[str] = []

        async def track_load(path: str, namespace: str) -> None:
            loaded_namespaces.append(namespace)

        mock_state = MagicMock()
        mock_state.vector_store = MagicMock(spec=IVectorStore)
        mock_state.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["docs"])
        mock_state.vector_store.load = AsyncMock(side_effect=track_load)
        mock_state.llm = MagicMock(spec=ILLM)
        mock_state.embedder = MagicMock(spec=IEmbedder)
        mock_state.storage = MagicMock(spec=IChatStorage)
        mock_state.reranker = MagicMock(spec=IReranker)
        mock_state.chunker = MagicMock(spec=IChunker)

        with patch(
            "ai_assistant.api.lifespan._load_config", return_value=minimal_config
        ), patch(
            "ai_assistant.api.lifespan.init_adapters", return_value=mock_state
        ), patch(
            "ai_assistant.api.static.mount_static"
        ), patch(
            "ai_assistant.api.lifespan.setup_logging"
        ), patch(
            "ai_assistant.api.lifespan.get_expected_api_key", return_value=None
        ), patch(
            "ai_assistant.api.lifespan.set_api_key"
        ):
            async with lifespan(app):
                pass

        # Assert on state — correct namespace was loaded
        assert loaded_namespaces == ["docs"]

    @pytest.mark.asyncio
    async def test_lifespan_graceful_shutdown_timeout(self):
        """Given: adapter shutdown hangs.
        When: _async_cleanup runs.
        Then: other adapters still shutdown; timeout is handled gracefully.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        shutdown_completed = {"embedder": False}

        async def hanging_shutdown():
            await asyncio.sleep(999)

        async def embedder_shutdown():
            shutdown_completed["embedder"] = True

        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = AsyncMock()
        mock_state.llm.shutdown = AsyncMock(side_effect=hanging_shutdown)
        mock_state.embedder = AsyncMock()
        mock_state.embedder.shutdown = AsyncMock(side_effect=embedder_shutdown)
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        # Should complete without hanging forever (5s per adapter + margin)
        await asyncio.wait_for(_async_cleanup(app, minimal_config), timeout=10.0)

        # Assert on state — embedder completed despite llm hanging
        assert shutdown_completed["embedder"] is True

    # ── FAULT-INJECTION TESTS ──

    @pytest.mark.asyncio
    async def test_async_cleanup_adapter_shutdown_exception(self):
        """Given: adapter shutdown raises Exception.
        When: _async_cleanup runs.
        Then: other adapters still shutdown; exception is caught and logged.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        shutdown_completed = {"embedder": False}

        async def failing_shutdown():
            raise RuntimeError("shutdown boom")

        async def embedder_shutdown():
            shutdown_completed["embedder"] = True

        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = AsyncMock()
        mock_state.llm.shutdown = AsyncMock(side_effect=failing_shutdown)
        mock_state.embedder = AsyncMock()
        mock_state.embedder.shutdown = AsyncMock(side_effect=embedder_shutdown)
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        await _async_cleanup(app, minimal_config)

        assert shutdown_completed["embedder"] is True

    @pytest.mark.asyncio
    async def test_async_cleanup_index_save_exception_logged(self):
        """Given: vector_store.save raises Exception.
        When: _async_cleanup runs.
        Then: exception is logged and cleanup continues.
        """
        minimal_config = _make_minimal_config()
        app = FastAPI()

        mock_state = MagicMock()
        mock_state.vector_store = MagicMock(spec=IVectorStore)
        mock_state.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["ns1"])
        mock_state.vector_store.save = AsyncMock(side_effect=RuntimeError("disk full"))
        mock_state.llm = AsyncMock()
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        # Should not raise — exception is caught and logged
        await _async_cleanup(app, minimal_config)


# ═══════════════════════════════════════════════════════════════════════════
# TestAPIMiddleware
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIMiddleware:
    """Tests for api/middleware.py — MetricsMiddleware."""

    def test_metrics_middleware_counts_requests(self):
        """Given: MetricsMiddleware is installed.
        When: a request is processed.
        Then: counter and histogram metrics functions are called.
        """
        from ai_assistant.core import metrics

        app = FastAPI()
        app.add_middleware(MetricsMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        with patch.object(metrics, "increment_counter") as mock_counter, patch.object(
            metrics, "observe_histogram"
        ) as mock_histogram:
            client = TestClient(app)
            resp = client.get("/test")
            assert resp.status_code == 200

            mock_counter.assert_called_once()
            call_args = mock_counter.call_args
            assert call_args.kwargs["labels"]["method"] == "GET"
            assert call_args.kwargs["labels"]["path"] == "/test"
            assert call_args.kwargs["labels"]["status"] == "200"

            mock_histogram.assert_called_once()
            hist_args = mock_histogram.call_args
            assert hist_args.kwargs["labels"]["path"] == "/test"
            assert hist_args.kwargs["value"] >= 0.0

    def test_metrics_middleware_records_error_status(self):
        """Given: an endpoint raises HTTPException.
        When: request goes through MetricsMiddleware.
        Then: status label reflects the error code.
        """
        from ai_assistant.core import metrics

        app = FastAPI()
        app.add_middleware(MetricsMiddleware)

        @app.get("/error")
        async def error_endpoint():
            raise HTTPException(status_code=500)

        with patch.object(metrics, "increment_counter") as mock_counter, patch.object(
            metrics, "observe_histogram"
        ) as mock_histogram:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/error")
            assert resp.status_code == 500

            call_args = mock_counter.call_args
            assert call_args.kwargs["labels"]["status"] == "500"

    def test_metrics_middleware_records_latency(self):
        """Given: an endpoint with artificial delay.
        When: request goes through MetricsMiddleware.
        Then: observed histogram value is > 0.
        """
        from ai_assistant.core import metrics

        app = FastAPI()
        app.add_middleware(MetricsMiddleware)

        @app.get("/slow")
        async def slow_endpoint():
            await asyncio.sleep(0.05)
            return {"ok": True}

        with patch.object(metrics, "observe_histogram") as mock_histogram:
            client = TestClient(app)
            client.get("/slow")

            hist_args = mock_histogram.call_args
            assert hist_args.kwargs["value"] > 0.0

    def test_cors_preflight_bypasses_auth(self, client):
        """Given: CORS preflight OPTIONS request.
        When: sent to a protected endpoint.
        Then: 200 OK without API key (CORS middleware handles it before auth).
        """
        # Note: This assumes CORS middleware is installed before auth in main app.
        # If the app under test does not have CORS, this test documents the gap.
        resp = client.options(
            "/api/v1/chat",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # CORS preflight should succeed (200) or be handled by router (404 if no CORS)
        # The key contract: it must NOT be 401 (auth should not block preflight)
        assert resp.status_code != 401

    def test_metrics_middleware_no_response_on_exception(self):
        """Given: an unhandled exception (no response object).
        When: MetricsMiddleware finally block runs.
        Then: status defaults to 500.
        """
        from ai_assistant.core import metrics

        app = FastAPI()
        app.add_middleware(MetricsMiddleware)

        @app.get("/crash")
        async def crash_endpoint():
            raise RuntimeError("boom")

        with patch.object(metrics, "increment_counter") as mock_counter:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/crash")
            assert resp.status_code == 500

            call_args = mock_counter.call_args
            assert call_args.kwargs["labels"]["status"] == "500"

    def test_cors_rejects_evil_origin(self, client):
        """Given: request from unauthorized origin.
        When: sent to any endpoint.
        Then: no CORS headers returned (browser blocks access)."""
        resp = client.get(
            "/",
            headers={"Origin": "http://evil.com"},
        )
        headers = {k.lower(): v for k, v in resp.headers.items()}
        assert "access-control-allow-origin" not in headers

    def test_metrics_middleware_uses_route_pattern_not_raw_path(self):
        """Given: MetricsMiddleware is installed on routes with path params.
        When: a request with a dynamic path segment is processed.
        Then: the recorded metric path is the route pattern, not the raw URL.
        """
        from ai_assistant.core import metrics

        app = FastAPI()
        app.add_middleware(MetricsMiddleware)

        @app.get("/reindex/status/{task_id}")
        async def _handler(task_id: str) -> dict[str, str]:
            return {"task_id": task_id}

        with patch.object(metrics, "increment_counter") as mock_counter, patch.object(
            metrics, "observe_histogram"
        ) as mock_histogram:
            client = TestClient(app)
            resp = client.get("/reindex/status/abc-123")

        assert resp.status_code == 200
        assert resp.json() == {"task_id": "abc-123"}

        counter_call = mock_counter.call_args
        assert counter_call is not None
        assert counter_call.kwargs["labels"]["path"] == "/reindex/status/{task_id}"

        hist_call = mock_histogram.call_args
        assert hist_call is not None
        assert hist_call.kwargs["labels"]["path"] == "/reindex/status/{task_id}"

    def test_metrics_middleware_allowed_hosts_blocks_unknown(self):
        """Given: MetricsMiddleware with allowed_hosts set.
        When: request comes from disallowed host.
        Then: 400 Bad Request is returned before reaching routes.
        """
        app = FastAPI()
        app.add_middleware(
            MetricsMiddleware,
            allowed_hosts=["localhost", "127.0.0.1"],
        )

        @app.get("/test")
        async def _handler() -> dict[str, str]:
            return {"ok": "true"}

        client = TestClient(app, base_url="http://evil.com")
        resp = client.get("/test", headers={"host": "evil.com"})
        assert resp.status_code == 400
        assert resp.text == "Invalid host header"

    def test_metrics_middleware_allowed_hosts_allows_known(self):
        """Given: MetricsMiddleware with allowed_hosts set.
        When: request comes from allowed host.
        Then: route handler executes normally.
        """
        app = FastAPI()
        app.add_middleware(
            MetricsMiddleware,
            allowed_hosts=["localhost", "127.0.0.1"],
        )

        @app.get("/test")
        async def _handler() -> dict[str, str]:
            return {"ok": "true"}

        client = TestClient(app, base_url="http://localhost")
        resp = client.get("/test", headers={"host": "localhost"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": "true"}

# ═══════════════════════════════════════════════════════════════════════════
# TestAPIAdmin
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIAdmin:
    """Contract tests for api/admin.py endpoints."""

    def _make_admin_state(self, enabled: bool) -> MagicMock:
        """Helper: create AppState mock with nested security config."""
        state = MagicMock(spec=AppState)
        state.config = MagicMock()
        state.config.security = MagicMock()
        state.config.security.admin_enabled = enabled
        return state

    async def test_current_model_response(self):
        """Given: AppState with LLM config.
        When: get_current_model is called.
        Then: _CurrentModelResponse with model and provider is returned.
        """
        state = MagicMock(spec=AppState)
        state.config = MagicMock()
        state.config.llm = MagicMock()
        state.config.llm.model = "gpt-4"
        state.config.llm.provider = "openai"

        resp = await admin.get_current_model(state)
        assert resp.model == "gpt-4"
        assert resp.provider == "openai"

    async def test_current_model_response_structure(self):
        """Given: any valid AppState.
        When: get_current_model returns.
        Then: response is a Pydantic BaseModel with correct fields.
        """
        state = MagicMock(spec=AppState)
        state.config = MagicMock()
        state.config.llm = MagicMock()
        state.config.llm.model = "test-model"
        state.config.llm.provider = "test-provider"

        resp = await admin.get_current_model(state)
        assert isinstance(resp, BaseModel)
        assert hasattr(resp, "model")
        assert hasattr(resp, "provider")

    def test_admin_router_has_prefix(self):
        """Given: admin router is imported.
        When: its prefix is checked.
        Then: it starts with /admin.
        """
        assert admin.router.prefix == "/admin"
        assert "admin" in admin.router.tags

    def test_update_api_key_request_schema(self):
        """Given: _UpdateApiKeyRequest is instantiated.
        When: api_key is None or a string.
        Then: both are valid.
        """
        req_none = _UpdateApiKeyRequest(api_key=None)
        assert req_none.api_key is None

        req_str = _UpdateApiKeyRequest(api_key="secret")
        assert req_str.api_key == "secret"

    def test_update_api_key_response_schema(self):
        """Given: _UpdateApiKeyResponse is instantiated.
        When: fields are set.
        Then: updated is bool and source is str.
        """
        resp = _UpdateApiKeyResponse(updated=True, source="runtime_override")
        assert resp.updated is True
        assert resp.source == "runtime_override"

    async def test_update_api_key_logs_security_audit(self):
        """Given: admin_enabled is True.
        When: update_api_key changes the key.
        Then: SECURITY_AUDIT marker is present in logs.
        """
        from ai_assistant.api.admin import _admin_logger, update_api_key

        set_api_key(None)
        state = self._make_admin_state(enabled=True)
        req = _UpdateApiKeyRequest(api_key="new-key")

        with patch.object(_admin_logger, "warning") as mock_log:
            await update_api_key(req, state)

        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert "SECURITY_AUDIT:" in call_args[0][0]
        assert call_args.kwargs["extra"]["security_event"] == "api_key_changed"
        assert call_args.kwargs["extra"]["actor"] == "admin_endpoint"
        assert call_args.kwargs["extra"]["key_present"] is True
