"""Direct tests for api/deps.py — AppState assembly and pipeline construction.

Validates that init_adapters correctly:
- Creates AppState with all expected fields
- Builds RAGPipeline with correct step lambdas
- Handles missing/optional adapters gracefully
- Respects sacred core boundaries (factory mocking)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.api.deps import (
    AppState,
    InitializedAppState,
    _STEP_MAP,
    get_state,
    init_adapters,
)
from ai_assistant.core.config import AppConfig, RAGStep
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY

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
        assert hasattr(state, "storage")
        assert hasattr(state, "chat_manager")
        assert hasattr(state, "limiter")

    def test_defaults_are_none_except_config(self):
        cfg = AppConfig()
        state = AppState(config=cfg)
        assert state.config is cfg
        assert state.embedder is None
        assert state.vector_store is None
        assert state.pipeline is None
        assert state.chat_manager is None
        assert state.limiter is None


# ── init_adapters with mocked factory ──


@pytest.fixture
def minimal_config():
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


class TestInitAdapters:
    @pytest.mark.asyncio
    async def test_app_state_assembled_correctly(self, minimal_config):
        """Mock create_adapter and verify AppState fields are populated."""
        mock_llm = MagicMock()
        mock_embedder = MagicMock()
        mock_vector_store = MagicMock()
        mock_chunker = MagicMock()
        mock_storage = MagicMock()
        mock_storage.init_db = AsyncMock()
        mock_reranker = MagicMock()

        # Mock list_namespaces and load for vector_store
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
    async def test_pipeline_created_with_correct_steps(self, minimal_config):
        """Verify pipeline steps are bound with correct dependencies."""
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
        # Should have 4 steps: embed_query, retrieve, build_context, generate
        assert len(result.pipeline.steps) == 4

        # Verify step callables accept PipelineData
        step_names = ["embed_query", "retrieve", "build_context", "generate"]
        for i, name in enumerate(step_names):
            assert callable(result.pipeline.steps[i]), f"Step {name} is not callable"

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

        step_names = ["embed_query", "retrieve", "build_context", "generate"]
        for i, name in enumerate(step_names):
            step = result.pipeline.steps[i]
            assert callable(step), f"Step {name} is not callable"
            # Class instances used for dependency-bound steps; lambdas have __name__ == '<lambda>'
            if name in ("embed_query", "retrieve", "build_context", "generate"):
                assert hasattr(step, "__call__"), f"Step {name} lacks __call__"
                assert getattr(step, "__name__", None) != "<lambda>", (
                    f"Step {name} is a lambda, expected class instance"
                )

    @pytest.mark.asyncio
    async def test_reranker_null_when_not_configured(self, minimal_config):
        """When reranker provider is missing, NullReranker is used."""
        from ai_assistant.adapters.reranker_null import NullReranker
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
    async def test_storage_raises_when_not_in_registry(self, minimal_config):
        """Storage adapter not available raises RuntimeError."""
        mock_vector_store = MagicMock()
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                raise ValueError("No storage adapter registered for 'sqlite'")
            return MagicMock()

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            with pytest.raises(RuntimeError, match="Storage adapter failed to initialize"):
                await init_adapters(minimal_config)

    @pytest.mark.asyncio
    async def test_storage_raises_on_import_error(self, minimal_config):
        """Storage adapter raising ImportError raises RuntimeError."""
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
            with pytest.raises(RuntimeError, match="Storage adapter failed to initialize"):
                await init_adapters(minimal_config)

    @pytest.mark.asyncio
    async def test_storage_raises_on_value_error(self, minimal_config):
        """Storage adapter raising ValueError raises RuntimeError."""
        mock_vector_store = MagicMock()
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_vector_store.load = AsyncMock(return_value=None)

        def fake_create_adapter(port: str, name: str, config: Any) -> Any:
            if port == "vector_store" and name == "memory":
                return mock_vector_store
            if port == "storage" and name == "sqlite":
                raise ValueError("Broken config")
            return MagicMock()

        with patch(
            "ai_assistant.api.deps.create_adapter", side_effect=fake_create_adapter
        ):
            with pytest.raises(RuntimeError, match="Storage adapter failed to initialize"):
                await init_adapters(minimal_config)

    @pytest.mark.asyncio
    async def test_init_adapters_returns_fresh_state(self, minimal_config):
        """init_adapters returns a fresh InitializedAppState each call."""
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
        assert result.config is minimal_config
        assert result.llm is not None
        assert result.embedder is not None
        assert result.vector_store is not None


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

    def test_raises_when_app_state_is_none(self):
        from fastapi import FastAPI, Request

        app = FastAPI()
        # app_state not set — defaults to None

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


class TestStepRegistry:
    def test_step_map_contains_all_standard_steps(self):
        for member in (
            RAGStep.EMBED_QUERY,
            RAGStep.RETRIEVE,
            RAGStep.RERANK,
            RAGStep.BUILD_CONTEXT,
            RAGStep.GENERATE,
        ):
            assert member in _STEP_MAP

    def test_step_map_contains_hyde(self):
        assert RAGStep.HYDE_QUERY in _STEP_MAP

    def test_step_map_is_dynamic_from_registry(self):
        assert all(isinstance(k, RAGStep) for k in _STEP_MAP.keys())
        for step_enum, func in _STEP_MAP.items():
            assert STEP_REGISTRY[step_enum.value] is func

    @pytest.mark.asyncio
    async def test_pipeline_with_hyde_step(self, minimal_config):
        """Pipeline can include hyde_query step."""
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

        assert result.pipeline is not None
        assert len(result.pipeline.steps) == 5
        step = result.pipeline.steps[1]
        assert callable(step)
        # Pipeline may wrap steps; verify identity by name, not object reference
        step_name = getattr(step, "__name__", None)
        if step_name is None and hasattr(step, "func"):
            step_name = getattr(step.func, "__name__", None)
        assert step_name == "hyde_query", (
            f"Expected hyde_query step, got {step_name!r}"
        )


class TestChatStoragePagination:
    @pytest.mark.asyncio
    async def test_get_history_accepts_offset(self):
        """IChatStorage.get_history must accept offset parameter."""
        from ai_assistant.core.ports.storage import IChatStorage

        class DummyStorage(IChatStorage):
            async def init_db(self) -> None:
                pass

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
