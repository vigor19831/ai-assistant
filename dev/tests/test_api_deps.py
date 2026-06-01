"""Direct tests for api/deps.py — AppState assembly and pipeline construction.

Validates that init_adapters correctly:
- Creates AppState with all expected fields
- Builds RAGPipeline with correct step lambdas
- Handles missing/optional adapters gracefully
- Respects sacred core boundaries (registry_create mocking)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.api.deps import AppState, MetricsMiddleware, get_state, init_adapters
from ai_assistant.core.config import AppConfig
from ai_assistant.core.pipeline import RAGPipeline

# ── AppState dataclass ──


class TestAppState:
    def test_has_all_expected_fields(self):
        state = AppState(config=AppConfig())
        assert hasattr(state, "config")
        assert hasattr(state, "embedder")
        assert hasattr(state, "vector_store")
        assert hasattr(state, "llm")
        assert hasattr(state, "chunker")
        assert hasattr(state, "reranker")
        assert hasattr(state, "pipeline")
        assert hasattr(state, "voice_recognizer")
        assert hasattr(state, "voice_synthesizer")
        assert hasattr(state, "vision")
        assert hasattr(state, "storage")
        assert hasattr(state, "tool_registry")
        assert hasattr(state, "long_term_memory")
        assert hasattr(state, "chat_manager")

    def test_defaults_are_none_except_config(self):
        cfg = AppConfig()
        state = AppState(config=cfg)
        assert state.config is cfg
        assert state.embedder is None
        assert state.vector_store is None
        assert state.pipeline is None
        assert state.chat_manager is None


# ── init_adapters with mocked registry.create ──


class TestInitAdapters:
    @pytest.fixture
    def minimal_config(self):
        """Config with only required providers."""
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

    @pytest.mark.asyncio
    async def test_app_state_assembled_correctly(self, minimal_config):
        """Mock registry.create and verify AppState fields are populated."""
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()
        mock_reranker = MagicMock()
        mock_tool = MagicMock()
        mock_memory = MagicMock()
        mock_memory.init_db = AsyncMock()

        # Mock list_namespaces and load for vector_store
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_registry_create(port: str, name: str, config: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("storage", "sqlite"): mock_storage,
                ("reranker", "dummy"): mock_reranker,
                ("tool", "calculator"): mock_tool,
                ("memory", "sqlite"): mock_memory,
            }
            return mapping.get((port, name), MagicMock())

        with patch(
            "ai_assistant.core.registry.create", side_effect=fake_registry_create
        ):
            state = AppState(config=minimal_config)
            await init_adapters(state)

        assert state.config is minimal_config
        assert state.llm is mock_llm
        assert state.embedder is mock_embedder
        assert state.vector_store is mock_vector_store
        assert state.chunker is mock_chunker
        assert state.storage is mock_storage
        assert state.reranker is mock_reranker
        assert state.tool_registry is not None
        assert state.chat_manager is not None

    @pytest.mark.asyncio
    async def test_pipeline_created_with_correct_steps(self, minimal_config):
        """Verify pipeline steps are bound with correct dependencies."""
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_reranker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.init_db = AsyncMock()

        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_registry_create(port: str, name: str, config: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("reranker", "dummy"): mock_reranker,
                ("tool", "calculator"): MagicMock(),
                ("storage", "sqlite"): mock_storage,
                ("memory", "sqlite"): mock_memory,
            }
            return mapping.get((port, name), MagicMock())

        with patch(
            "ai_assistant.core.registry.create", side_effect=fake_registry_create
        ):
            state = AppState(config=minimal_config)
            await init_adapters(state)

        assert state.pipeline is not None
        assert isinstance(state.pipeline, RAGPipeline)
        # Should have 4 steps: embed_query, retrieve, build_context, generate
        assert len(state.pipeline.steps) == 4

        # Verify step callables accept PipelineData
        step_names = ["embed_query", "retrieve", "build_context", "generate"]
        for i, name in enumerate(step_names):
            assert callable(state.pipeline.steps[i]), f"Step {name} is not callable"

    @pytest.mark.asyncio
    async def test_pipeline_steps_are_callable_objects_not_lambdas(
        self, minimal_config
    ):
        """Verify bound steps are class instances with __call__, not lambdas."""
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_reranker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.init_db = AsyncMock()

        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_registry_create(port: str, name: str, config: Any) -> Any:
            mapping = {
                ("llm", "mock"): mock_llm,
                ("embedder", "mock"): mock_embedder,
                ("vector_store", "memory"): mock_vector_store,
                ("chunker", "simple"): mock_chunker,
                ("reranker", "dummy"): mock_reranker,
                ("tool", "calculator"): MagicMock(),
                ("storage", "sqlite"): mock_storage,
                ("memory", "sqlite"): mock_memory,
            }
            return mapping.get((port, name), MagicMock())

        with patch(
            "ai_assistant.core.registry.create", side_effect=fake_registry_create
        ):
            state = AppState(config=minimal_config)
            await init_adapters(state)

        assert state.pipeline is not None
        assert isinstance(state.pipeline, RAGPipeline)
        assert len(state.pipeline.steps) == 4

        step_names = ["embed_query", "retrieve", "build_context", "generate"]
        for i, name in enumerate(step_names):
            step = state.pipeline.steps[i]
            assert callable(step), f"Step {name} is not callable"
            # Class instances used for dependency-bound steps; lambdas have __name__ == '<lambda>'
            if name in ("embed_query", "retrieve", "generate"):
                assert hasattr(step, "__call__"), f"Step {name} lacks __call__"
                assert getattr(step, "__name__", None) != "<lambda>", (
                    f"Step {name} is a lambda, expected class instance"
                )

    @pytest.mark.asyncio
    async def test_reranker_none_when_not_configured(self, minimal_config):
        """When reranker provider is missing, reranker should be None."""
        minimal_config.reranker.provider = "nonexistent"

        mock_vector_store = MagicMock()
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()
        mock_memory = MagicMock()
        mock_memory.init_db = AsyncMock()

        def fake_registry_create(port: str, name: str, config: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "reranker" and name == "nonexistent":
                raise ValueError("No such reranker")
            if port == "storage" and name == "sqlite":
                return mock_storage
            if port == "memory" and name == "sqlite":
                return mock_memory
            return MagicMock()

        with patch(
            "ai_assistant.core.registry.create", side_effect=fake_registry_create
        ):
            state = AppState(config=minimal_config)
            await init_adapters(state)

        assert state.reranker is None

    @pytest.mark.asyncio
    async def test_storage_none_when_registry_fails(self, minimal_config):
        """Storage adapter failure should set storage to None, not crash."""
        mock_vector_store = MagicMock()
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)
        mock_memory = MagicMock()
        mock_memory.init_db = AsyncMock()

        def fake_registry_create(port: str, name: str, config: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                raise ValueError("No storage adapter")
            if port == "memory" and name == "sqlite":
                return mock_memory
            return MagicMock()

        with patch(
            "ai_assistant.core.registry.create", side_effect=fake_registry_create
        ):
            state = AppState(config=minimal_config)
            await init_adapters(state)

        assert state.storage is None

    @pytest.mark.asyncio
    async def test_idempotent_init(self, minimal_config):
        """Multiple calls to init_adapters should return same state
        without re-creating adapters."""
        call_count = {"count": 0}

        def counting_registry_create(port: str, name: str, config: Any) -> Any:
            call_count["count"] += 1
            m = MagicMock()
            if port == "vector_store":
                m.list_namespaces = AsyncMock(return_value=[])
                m.load = AsyncMock(return_value=None)
            if port in ("storage", "memory"):
                m.init_db = AsyncMock()
            return m

        with patch(
            "ai_assistant.core.registry.create",
            side_effect=counting_registry_create,
        ):
            state = AppState(config=minimal_config)
            first_result = await init_adapters(state)
            first_count = call_count["count"]
            second_result = await init_adapters(state)
            second_count = call_count["count"]

        assert second_count == first_count, "Second init should not re-create adapters"
        assert first_result is second_result, "Should return same state object"
        assert first_result is state, "Should return original state"


# ── MetricsMiddleware ──


class TestMetricsMiddleware:
    @pytest.mark.asyncio
    async def test_logs_request_metrics(self):
        """Middleware should record latency and token metrics."""
        from starlette.requests import Request
        from starlette.responses import Response as StarletteResponse

        middleware = MetricsMiddleware(MagicMock())

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/test"

        mock_response = MagicMock(spec=StarletteResponse)
        mock_response.status_code = 200

        async def mock_call_next(request: Request):
            return mock_response

        with patch(
            "ai_assistant.core.metrics.get_current_metrics",
            return_value={"input_tokens": 10, "output_tokens": 5},
        ):
            with patch("ai_assistant.core.metrics.get_metrics_logger") as mock_logger:
                mock_logger.return_value.log = MagicMock()
                result = await middleware.dispatch(mock_request, mock_call_next)
                assert result is mock_response
                mock_logger.return_value.log.assert_called_once()
                record = mock_logger.return_value.log.call_args[0][0]
                assert record["endpoint"] == "/test"
                assert record["status_code"] == 200
                assert "latency_ms" in record


# ── get_state error handling ──


class TestGetState:
    def test_raises_when_not_initialized(self):
        from fastapi import FastAPI, Request

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

    def test_reads_from_app_state(self):
        from fastapi import FastAPI, Request

        app = FastAPI()
        mock_state = AppState(config=AppConfig())
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

    def test_fallback_to_singleton_when_app_state_is_wrong_type(self):
        from fastapi import FastAPI, Request
        from ai_assistant.api.deps import set_state

        app = FastAPI()
        app.state.app_state = "not an AppState"

        mock_state = AppState(config=AppConfig())
        set_state(mock_state)

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

    def test_raises_when_app_state_is_wrong_type_and_singleton_uninitialized(self):
        from fastapi import FastAPI, Request

        app = FastAPI()
        app.state.app_state = "not an AppState"

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

# ── IChatStorage pagination ──


class TestChatStoragePagination:
    @pytest.mark.asyncio
    async def test_get_history_accepts_offset(self):
        """IChatStorage.get_history must accept offset parameter."""
        from ai_assistant.core.ports.storage import IChatStorage

        class DummyStorage(IChatStorage):
            async def save_message(self, conversation_id: str, message: dict[str, Any]) -> None:
                pass

            async def get_history(
                self, conversation_id: str, limit: int = 50, offset: int = 0
            ) -> list[dict[str, Any]]:
                return [{"offset": offset, "limit": limit}]

        storage = DummyStorage(config=MagicMock())
        result = await storage.get_history("conv-1", limit=10, offset=5)
        assert result[0]["offset"] == 5
        assert result[0]["limit"] == 10

    @pytest.mark.asyncio
    async def test_sqlite_storage_pagination(self, tmp_path):
        """SQLiteStorage.get_history respects LIMIT and OFFSET.

        ORDER BY id DESC + reversed(rows) means:
        - Pages go from newest to oldest.
        - Within a page, messages are oldest-first.
        """
        from ai_assistant.adapters.storage_sqlite import SQLiteStorage

        cfg = MagicMock()
        cfg.db_path = str(tmp_path / "test_pag.db")
        storage = SQLiteStorage(cfg)
        await storage.init_db()

        # Insert 5 messages: id 1..5
        for i in range(5):
            await storage.save_message(
                "conv-1",
                {"role": "user", "content": f"msg-{i}", "metadata": {}},
            )

        # Page 1: limit=2, offset=0 → ids 5,4 (newest) → reversed → 4,5
        page1 = await storage.get_history("conv-1", limit=2, offset=0)
        assert len(page1) == 2
        assert page1[0]["content"] == "msg-3"
        assert page1[1]["content"] == "msg-4"

        # Page 2: limit=2, offset=2 → ids 3,2 → reversed → 2,3
        page2 = await storage.get_history("conv-1", limit=2, offset=2)
        assert len(page2) == 2
        assert page2[0]["content"] == "msg-1"
        assert page2[1]["content"] == "msg-2"

        # Page 3: limit=2, offset=4 → id 1 → reversed → 1
        page3 = await storage.get_history("conv-1", limit=2, offset=4)
        assert len(page3) == 1
        assert page3[0]["content"] == "msg-0"

        # Page 4: limit=2, offset=6 → empty
        page4 = await storage.get_history("conv-1", limit=2, offset=6)
        assert page4 == []