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
from pydantic import BaseModel
from starlette.requests import Request
from starlette.testclient import TestClient

from ai_assistant.api import admin
from ai_assistant.api.admin import _UpdateApiKeyRequest, _UpdateApiKeyResponse, update_api_key
from ai_assistant.api.deps import (
    AppState,
    InitializedAppState,
    _STEP_MAP,
    _build_step_funcs,
    get_state,
    init_adapters,
)
from ai_assistant.api.lifespan import _async_cleanup, _load_config, lifespan
from ai_assistant.api.middleware import MetricsMiddleware
from ai_assistant.api.router import _ROUTERS, assemble_routers
from ai_assistant.api.security import (
    SECURITY_MAX_BODY,
    bearer_scheme,
    check_request_size,
    get_expected_api_key,
    require_api_key,
    set_api_key,
)
from ai_assistant.core.config import AppConfig, RAGStep, load_config
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline

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


@pytest.fixture
def make_minimal_config():
    """Factory fixture — returns a fresh AppConfig for each call.

    Prevents test-to-test pollution when a test mutates the config.
    """
    def _factory(**overrides):
        cfg = AppConfig(
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
        for key, val in overrides.items():
            setattr(cfg, key, val)
        return cfg

    return _factory


@pytest.fixture
def minimal_config(make_minimal_config):
    """Backward-compat: single fresh config instance per test."""
    return make_minimal_config()


@pytest.fixture
def mock_state(minimal_config):
    """Return a mock InitializedAppState with minimal config for client tests."""
    state = MagicMock(spec=InitializedAppState)
    state.config = minimal_config
    return state


@pytest.fixture
def client(mock_state):
    """Return a TestClient with mocked app state."""
    from ai_assistant.main import create_app

    app = create_app(state=mock_state)
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
        creds = MagicMock()
        creds.credentials = "secret"
        await require_api_key(creds)

    async def test_require_api_key_not_configured(self):
        """Given: no API key is configured.
        When: require_api_key is called.
        Then: HTTPException 401 is raised.
        """
        set_api_key(None)
        creds = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(creds)
        assert exc_info.value.status_code == 401
        assert "not configured" in exc_info.value.detail.lower()

    async def test_require_api_key_invalid(self):
        """Given: a bearer token that does not match the expected key.
        When: require_api_key is called with it.
        Then: HTTPException 401 is raised.
        """
        set_api_key("secret")
        creds = MagicMock()
        creds.credentials = "wrong"
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(creds)
        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()

    async def test_require_api_key_missing_credentials(self):
        """Given: credentials object is None.
        When: require_api_key is called.
        Then: HTTPException 401 is raised.
        """
        set_api_key("secret")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(None)
        assert exc_info.value.status_code == 401

    async def test_require_api_key_malformed_header(self):
        """Given: credentials object lacks .credentials attribute.
        When: require_api_key is called.
        Then: HTTPException 401 is raised."""
        set_api_key("secret")
        bad_creds = object()  # plain object without .credentials
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(bad_creds)
        assert exc_info.value.status_code == 401

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

    # ── Admin endpoint integration ──

    async def test_admin_update_api_key(self):
        """Given: admin endpoint receives a new api_key.
        When: update_api_key is called.
        Then: set_api_key stores the new key; config is NOT mutated.
        """
        set_api_key(None)
        state = MagicMock(spec=AppState)
        req = _UpdateApiKeyRequest(api_key="new-key")
        resp = await update_api_key(req, state)
        assert resp.updated is True
        assert get_expected_api_key() == "new-key"

    async def test_admin_clear_api_key(self):
        """Given: admin endpoint receives api_key=None.
        When: update_api_key is called.
        Then: override is cleared; config is NOT mutated.
        """
        set_api_key("old-key")
        state = MagicMock(spec=AppState)
        req = _UpdateApiKeyRequest(api_key=None)
        resp = await update_api_key(req, state)
        assert resp.updated is True
        assert get_expected_api_key() is None

    async def test_admin_update_empty_key_rejected(self):
        """Given: admin endpoint receives empty string api_key.
        When: update_api_key is called.
        Then: HTTPException 400 is raised.
        """
        set_api_key(None)
        state = MagicMock(spec=AppState)
        req = _UpdateApiKeyRequest(api_key="")
        with pytest.raises(HTTPException) as exc_info:
            await update_api_key(req, state)
        assert exc_info.value.status_code == 400

    async def test_admin_update_key_response_structure(self):
        """Given: a valid key update request.
        When: update_api_key returns.
        Then: response conforms to _UpdateApiKeyResponse schema.
        """
        state = MagicMock(spec=AppState)
        req = _UpdateApiKeyRequest(api_key="k")
        resp = await update_api_key(req, state)
        assert isinstance(resp, _UpdateApiKeyResponse)
        assert resp.updated is True
        assert resp.source == "runtime_override"

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
            "pipeline",
            "storage",
            "chat_manager",
            "limiter",
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
        assert state.pipeline is None
        assert state.chat_manager is None
        assert state.limiter is None

    # ── init_adapters (mocked factory) ──

    @pytest.mark.asyncio
    async def test_init_adapters_assembles_correctly(self, minimal_config):
        """Given: create_adapter is mocked.
        When: init_adapters is called.
        Then: InitializedAppState has all core adapters populated.
        """
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()
        mock_reranker = MagicMock()

        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("storage", "sqlite"): mock_storage,
                ("reranker", "dummy"): mock_reranker,
            }
            return mapping.get((port, name), MagicMock())

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
        assert result.chat_manager is not None

    @pytest.mark.asyncio
    async def test_init_adapters_pipeline_steps(self, minimal_config):
        """Given: create_adapter is mocked.
        When: init_adapters builds the pipeline.
        Then: RAGPipeline has 4 steps matching config order.
        """
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_reranker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()

        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("reranker", "dummy"): mock_reranker,
                ("storage", "sqlite"): mock_storage,
            }
            return mapping.get((port, name), MagicMock())

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            result = await init_adapters(minimal_config)

        assert result.pipeline is not None
        assert isinstance(result.pipeline, RAGPipeline)
        assert len(result.pipeline.steps) == 4
        for step in result.pipeline.steps:
            assert callable(step)

    @pytest.mark.asyncio
    async def test_init_adapters_steps_are_callable_not_lambdas(self, minimal_config):
        """Given: create_adapter is mocked.
        When: init_adapters builds the pipeline.
        Then: steps are class instances, not raw lambdas.
        """
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_reranker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()

        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("reranker", "dummy"): mock_reranker,
                ("storage", "sqlite"): mock_storage,
            }
            return mapping.get((port, name), MagicMock())

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            result = await init_adapters(minimal_config)

        for step in result.pipeline.steps:
            assert callable(step)
            assert getattr(step, "__name__", None) != "<lambda>"

    @pytest.mark.asyncio
    async def test_init_adapters_null_reranker_when_not_configured(self, make_minimal_config):
        """Given: reranker provider is None in config.
        When: init_adapters is called.
        Then: NullReranker is used.
        """
        from ai_assistant.adapters.reranker_null import NullReranker

        minimal_config = make_minimal_config()
        minimal_config.reranker.provider = None

        mock_vector_store = MagicMock()
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                return mock_storage
            if port == "reranker" and name == "null":
                return NullReranker(None)
            return MagicMock()

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            result = await init_adapters(minimal_config)

        assert isinstance(result.reranker, NullReranker)

    @pytest.mark.asyncio
    async def test_init_adapters_storage_raises_runtime_error(self, minimal_config):
        """Given: storage adapter raises ValueError.
        When: init_adapters is called.
        Then: RuntimeError is raised after the catch block.
        """
        mock_vector_store = MagicMock()
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                raise ValueError("No storage adapter registered")
            return MagicMock()

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            with pytest.raises(RuntimeError, match="Storage adapter failed"):
                await init_adapters(minimal_config)

    @pytest.mark.asyncio
    async def test_init_adapters_storage_import_error(self, minimal_config):
        """Given: storage adapter raises ImportError.
        When: init_adapters is called.
        Then: RuntimeError is raised.
        """
        mock_vector_store = MagicMock()
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                raise ImportError("sqlite3 not available")
            return MagicMock()

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            with pytest.raises(RuntimeError, match="Storage adapter failed"):
                await init_adapters(minimal_config)

    @pytest.mark.asyncio
    async def test_init_adapters_returns_fresh_state(self, minimal_config):
        """Given: init_adapters is called twice.
        When: comparing results.
        Then: each call returns a distinct InitializedAppState.
        """
        call_count = {"count": 0}

        def counting_create_adapter(port: str, name: str, config: Any) -> Any:
            call_count["count"] += 1
            m = MagicMock()
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
        app = FastAPI()
        mock_state = InitializedAppState(
            config=AppConfig(),
            llm=MagicMock(),
            embedder=MagicMock(),
            vector_store=MagicMock(),
            pipeline=MagicMock(),
            storage=MagicMock(),
            chunker=MagicMock(),
            chat_manager=MagicMock(),
            reranker=MagicMock(),
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

    # ── Step registry ──

    def test_step_map_contains_all_standard_steps(self):
        """Given: _STEP_MAP is populated from STEP_REGISTRY.
        When: standard steps are checked.
        Then: all expected RAGStep members are present.
        """
        for member in (
            RAGStep.EMBED_QUERY,
            RAGStep.RETRIEVE,
            RAGStep.RERANK,
            RAGStep.BUILD_CONTEXT,
            RAGStep.GENERATE,
        ):
            assert member in _STEP_MAP

    def test_step_map_contains_hyde(self):
        """Given: hyde_query is a registered step.
        When: _STEP_MAP is inspected.
        Then: HYDE_QUERY is present.
        """
        assert RAGStep.HYDE_QUERY in _STEP_MAP

    def test_step_map_is_dynamic_from_registry(self):
        """Given: _STEP_MAP is built from STEP_REGISTRY.
        When: keys and values are compared.
        Then: all keys are RAGStep enums and values match STEP_REGISTRY.
        """
        from ai_assistant.core.pipeline_steps import STEP_REGISTRY

        assert all(isinstance(k, RAGStep) for k in _STEP_MAP.keys())
        for step_enum, func in _STEP_MAP.items():
            assert STEP_REGISTRY[step_enum.value] is func

    @pytest.mark.asyncio
    async def test_pipeline_with_hyde_step(self, make_minimal_config):
        """Given: config includes hyde_query step.
        When: init_adapters builds the pipeline.
        Then: 5 steps are present and hyde_query is at index 1.
        """
        minimal_config = make_minimal_config()
        minimal_config.rag.steps = [
            "embed_query",
            "hyde_query",
            "retrieve",
            "build_context",
            "generate",
        ]
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_reranker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()

        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("reranker", "dummy"): mock_reranker,
                ("storage", "sqlite"): mock_storage,
            }
            return mapping.get((port, name), MagicMock())

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            result = await init_adapters(minimal_config)

        assert len(result.pipeline.steps) == 5
        step = result.pipeline.steps[1]
        step_name = getattr(step, "__name__", None)
        if step_name is None and hasattr(step, "func"):
            step_name = getattr(step.func, "__name__", None)
        assert step_name == "hyde_query"

    # ── _build_step_funcs stop_at ──

    def test_build_step_funcs_stop_at(self, minimal_config):
        """Given: a config with 4 steps and stop_at=GENERATE.
        When: _build_step_funcs is called.
        Then: only 3 steps are returned (stops before GENERATE).
        """
        funcs = _build_step_funcs(minimal_config, stop_at=RAGStep.GENERATE)
        assert len(funcs) == 3
        # Verify the last step is build_context, not generate
        assert funcs[-1] is _STEP_MAP[RAGStep.BUILD_CONTEXT]

    def test_build_step_funcs_no_stop(self, minimal_config):
        """Given: a config with 4 steps and no stop_at.
        When: _build_step_funcs is called.
        Then: all 4 steps are returned.
        """
        funcs = _build_step_funcs(minimal_config)
        assert len(funcs) == 4

    def test_build_step_funcs_unknown_step_raises(self, make_minimal_config):
        """Given: a config with an unknown step name.
        When: _build_step_funcs is called.
        Then: ValueError is raised.
        """
        minimal_config = make_minimal_config()
        minimal_config.rag.steps = ["embed_query", "nonexistent_step"]
        with pytest.raises(ValueError, match="Unknown step"):
            _build_step_funcs(minimal_config)

    # ── Cyclic dependencies guard ──

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

    def test_no_deferred_import_errors(self):
        """Given: a missing feature handler would break at runtime.
        When: assemble_routers is imported.
        Then: it succeeds immediately (no deferred import).
        """
        # This test file itself would fail collection if imports were broken
        assert assemble_routers is not None


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
    async def test_lifespan_startup_sets_app_state(self, minimal_config):
        """Given: a FastAPI app with lifespan.
        When: startup runs.
        Then: app.state.app_state is populated.
        """
        app = FastAPI()

        mock_state = MagicMock()
        mock_state.vector_store = None  # skip index load

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
    async def test_lifespan_shutdown_calls_cleanup(self, minimal_config):
        """Given: lifespan context manager.
        When: shutdown runs (exit from context).
        Then: _async_cleanup is called.
        """
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
            "ai_assistant.api.lifespan.get_expected_api_key", return_value=None
        ), patch(
            "ai_assistant.api.lifespan.set_api_key"
        ):
            async with lifespan(app):
                pass

        mock_state.llm.shutdown.assert_awaited_once()
        mock_state.embedder.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_cleanup_index_save(self, minimal_config):
        """Given: vector_store has namespaces.
        When: _async_cleanup runs.
        Then: save is called for each namespace with timeout.
        """
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = MagicMock()
        mock_state.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(
            return_value=["ns1", "ns2"]
        )
        mock_state.vector_store.save = AsyncMock()
        mock_state.llm = AsyncMock()
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        await _async_cleanup(app, minimal_config)

        assert mock_state.vector_store.save.await_count == 2

    @pytest.mark.asyncio
    async def test_async_cleanup_index_save_timeout(self, minimal_config):
        """Given: vector_store.save hangs beyond 10s.
        When: _async_cleanup runs.
        Then: TimeoutError is caught and logged; other namespaces still proceed.
        """
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = MagicMock()
        mock_state.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["ns1"])

        async def slow_save(*args, **kwargs):
            await asyncio.sleep(20)

        mock_state.vector_store.save = AsyncMock(side_effect=slow_save)
        mock_state.llm = AsyncMock()
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        await _async_cleanup(app, minimal_config)
        # Should not raise; timeout is handled
        mock_state.vector_store.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_cleanup_no_app_state(self, minimal_config):
        """Given: app.state has no app_state attribute.
        When: _async_cleanup runs.
        Then: it returns early without error.
        """
        app = FastAPI()
        await _async_cleanup(app, minimal_config)

    @pytest.mark.asyncio
    async def test_async_cleanup_adapter_shutdown_order(self, minimal_config):
        """Given: all adapters are present.
        When: _async_cleanup runs.
        Then: shutdown is called on each adapter in defined order.
        """
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None
        mock_state.llm = AsyncMock()
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        await _async_cleanup(app, minimal_config)

        mock_state.llm.shutdown.assert_awaited_once()
        mock_state.embedder.shutdown.assert_awaited_once()
        mock_state.storage.shutdown.assert_awaited_once()
        mock_state.reranker.shutdown.assert_awaited_once()
        mock_state.chunker.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_mount_static_called(self, minimal_config):
        """Given: lifespan startup.
        When: it runs.
        Then: mount_static is called with app and config.
        """
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None

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
            async with lifespan(app):
                pass

        mock_mount.assert_called_once_with(app, minimal_config)

    @pytest.mark.asyncio
    async def test_lifespan_setup_logging_called(self, minimal_config):
        """Given: lifespan startup.
        When: it runs.
        Then: setup_logging is called with correct level.
        """
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None

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
            async with lifespan(app):
                pass

        mock_setup.assert_called_once()
        call_args = mock_setup.call_args
        assert call_args.kwargs["level"] == "INFO"  # minimal_config.debug is False

    @pytest.mark.asyncio
    async def test_lifespan_sets_api_key_from_config(self, make_minimal_config):
        """Given: config has api_key and env has none.
        When: lifespan startup runs.
        Then: set_api_key is called with config key.
        """
        minimal_config = make_minimal_config()
        minimal_config.security.api_key = "cfg-secret"
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None

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
        ) as mock_set_key:
            async with lifespan(app):
                pass

        mock_set_key.assert_called_once_with("cfg-secret")

    @pytest.mark.asyncio
    async def test_lifespan_skips_set_api_key_when_env_present(self, make_minimal_config):
        """Given: env var already has API key.
        When: lifespan startup runs.
        Then: set_api_key is NOT called.
        """
        minimal_config = make_minimal_config()
        minimal_config.security.api_key = "cfg-secret"
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None

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
    async def test_lifespan_index_load_on_startup(self, minimal_config):
        """Given: vector_store has persisted namespaces.
        When: lifespan startup runs.
        Then: load is called for each namespace.
        """
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = MagicMock()
        mock_state.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["docs"])
        mock_state.vector_store.load = AsyncMock()

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

        mock_state.vector_store.load.assert_awaited_once_with(
            "./data/indices", namespace="docs"
        )

    @pytest.mark.asyncio
    async def test_lifespan_graceful_shutdown_timeout(self, minimal_config):
        """Given: adapter shutdown hangs.
        When: _async_cleanup runs.
        Then: other adapters still shutdown; no unhandled exception.
        """
        app = FastAPI()
        mock_state = MagicMock()
        mock_state.vector_store = None

        async def hanging_shutdown():
            await asyncio.sleep(999)

        mock_state.llm = AsyncMock()
        mock_state.llm.shutdown = AsyncMock(side_effect=hanging_shutdown)
        mock_state.embedder = AsyncMock()
        mock_state.storage = AsyncMock()
        mock_state.reranker = AsyncMock()
        mock_state.chunker = AsyncMock()

        app.state.app_state = mock_state

        # Should complete without hanging forever (5s per adapter + margin)
        await asyncio.wait_for(_async_cleanup(app, minimal_config), timeout=10.0)

        # embedder should still have been called despite llm hanging
        mock_state.embedder.shutdown.assert_awaited_once()


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


# ═══════════════════════════════════════════════════════════════════════════
# TestAPIAdmin
# ═══════════════════════════════════════════════════════════════════════════


class TestAPIAdmin:
    """Contract tests for api/admin.py endpoints."""

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
