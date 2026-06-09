"""End-to-end API tests — works both offline (TestClient) and online (real server).

Offline: mocked state via TestClient — 100% reliable, no server needed.
Online: real HTTP calls when server detected — validates actual deployment.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.core.config import AppConfig, NamespaceConfig
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata


# ── Fixtures ──

@pytest.fixture(autouse=True)
def _setup_namespaces(mock_state):
    """Ensure mock_state has per-namespace config for tests."""
    if not getattr(mock_state.config, "namespaces", None):
        mock_state.config.namespaces = {
            "personal": NamespaceConfig(threshold=0.1, chunk_size=512, prompt="rag_strict"),
            "work": NamespaceConfig(threshold=0.3, chunk_size=1024, prompt="rag_creative"),
            "other": NamespaceConfig(),
            "code": NamespaceConfig(),
            "books": NamespaceConfig(),
        }


# ── Offline Tests (TestClient) ──


class TestHealthOffline:
    """GET /health — always available, no deps."""

    def test_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_unauthorized_access(self, client, monkeypatch):
        """When API key is configured, unauthorized requests should fail."""
        monkeypatch.setattr(
            "ai_assistant.api.security.get_expected_api_key", lambda: "real-key"
        )
        resp = client.post(
            "/api/v1/chat",
            json={"message": "test"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401


class TestInfoOffline:
    """Tests for /info endpoint — public, no auth required."""

    def test_openai_compatible_model_name(self, client, mock_state):
        mock_state.config.llm.provider = "openai_compatible"
        mock_state.config.llm.model = "gemma3:4b"
        resp = client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "openai_compatible"
        assert data["llm_model"] == "gemma3:4b"
        assert data["app_name"] == "ai-assistant-test"
        assert data["config_version"] == "1.5.0"
        assert data["debug"] is False

    def test_mock_provider(self, client, mock_state):
        mock_state.config.llm.provider = "mock"
        mock_state.config.llm.model = "mock"
        resp = client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "mock"
        assert data["llm_model"] == "mock"

    def test_unknown_provider(self, client, mock_state):
        mock_state.config.llm.provider = "custom"
        resp = client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "custom"


class TestChatOffline:
    """POST /api/v1/chat and /api/v1/chat/stream — full chat feature."""

    def test_text_only(self, client):
        resp = client.post(
            "/api/v1/chat", json={"message": "Hello", "conversation_id": "test-123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["conversation_id"] == "test-123"
        assert data["role"] == "assistant"

    def test_generates_conversation_id(self, client):
        resp = client.post("/api/v1/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        assert resp.json()["conversation_id"]  # auto-generated UUID

    def test_empty_message(self, client):
        """Empty message should still return 200 (handled by manager)."""
        resp = client.post(
            "/api/v1/chat", json={"message": " ", "conversation_id": "test"}
        )
        assert resp.status_code == 200

    def test_stream_returns_sse(self, client):
        resp = client.post(
            "/api/v1/chat/stream",
            json={"message": "Hello", "conversation_id": "test"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        text = resp.text
        assert "data: " in text
        assert "[DONE]" in text

    def test_chat_handler_passes_trace_id(self, client, mock_state):
        """trace_id must be passed from handler through chat_manager to metadata."""
        captured_meta = {}

        async def capture_chat(*args, **kwargs):
            captured_meta["metadata"] = kwargs.get("metadata", {})
            return MagicMock(text="OK", metadata={}, tool_calls=[])

        mock_state.chat_manager.chat = capture_chat

        resp = client.post(
            "/api/v1/chat",
            json={"message": "Hello", "conversation_id": "test-trace"},
        )
        assert resp.status_code == 200
        assert "trace_id" in captured_meta["metadata"]
        assert captured_meta["metadata"]["trace_id"]


class TestOpenAICompatibleOffline:
    """OpenAI-compatible endpoints for Page Assist."""

    def test_list_models(self, client):
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        assert all("id" in m for m in data["data"])

    def test_chat_completions_non_stream(self, client):
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert data["choices"][0]["finish_reason"] == "stop"

    def test_chat_completions_stream(self, client):
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        assert "data:" in resp.text
        assert "[DONE]" in resp.text

    def test_openai_handler_passes_trace_id(self, client, mock_state):
        """OpenAI-compatible handler must pass trace_id to chat_manager."""
        captured_meta = {}

        async def capture_chat(*args, **kwargs):
            captured_meta["metadata"] = kwargs.get("metadata", {})
            return MagicMock(text="OK", metadata={}, tool_calls=[])

        mock_state.chat_manager.chat = capture_chat

        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert resp.status_code == 200
        assert "trace_id" in captured_meta["metadata"]
        assert captured_meta["metadata"]["trace_id"]


class TestRAGOffline:
    """POST /api/v1/rag/* — indexing, query, delete, health, namespaces."""

    def test_index_documents(self, client, mock_state):
        mock_state.chunker.chunk = AsyncMock(
            return_value=[
                Chunk(
                    id="c1",
                    text="chunk1",
                    metadata=ChunkMetadata(source="d1", index=0, total_chunks=1),
                )
            ]
        )
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        mock_state.vector_store.add = AsyncMock(return_value=None)
        mock_state.vector_store.save = AsyncMock(return_value=None)

        resp = client.post(
            "/api/v1/rag/index",
            json={
                "documents": [{"id": "d1", "content": "hello world", "metadata": {}}],
                "namespace": "test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["indexed_count"] == 1
        assert data["namespace"] == "test"

    def test_index_empty_content(self, client, mock_state):
        mock_state.chunker.chunk = AsyncMock(return_value=[])
        resp = client.post(
            "/api/v1/rag/index",
            json={
                "documents": [{"id": "d1", "content": "", "metadata": {}}],
                "namespace": "test",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["indexed_count"] == 0
        assert len(resp.json()["errors"]) > 0

    def test_delete_chunks(self, client, mock_state):
        mock_state.vector_store.delete = AsyncMock(return_value=None)
        resp = client.post(
            "/api/v1/rag/delete", json={"chunk_ids": ["c1"], "namespace": "test"}
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_chunks"] == 1

    def test_delete_by_document_ids(self, client, mock_state):
        mock_state.vector_store.list_by_filter = AsyncMock(
            return_value=[("c1", {"source": "d1"})]
        )
        mock_state.vector_store.delete = AsyncMock(return_value=None)
        resp = client.post(
            "/api/v1/rag/delete",
            json={"document_ids": ["d1"], "namespace": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_chunks"] == 1

    def test_health(self, client, mock_state):
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["default"])
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[("c1", {})])
        mock_state.embedder.dimension = 384
        resp = client.get("/api/v1/rag/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["index_loaded"] is True
        assert data["embedder_dim"] == 384

    def test_list_namespaces(self, client, mock_state):
        mock_state.config.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(
            return_value=["personal", "work"]
        )
        resp = client.get("/api/v1/rag/namespaces")
        assert resp.status_code == 200
        assert "personal" in resp.json()["namespaces"]
        assert "work" in resp.json()["namespaces"]

    def test_list_namespaces_empty_fallback(self, client, mock_state):
        mock_state.config.vector_store.index_path = None
        resp = client.get("/api/v1/rag/namespaces")
        assert resp.status_code == 200
        assert resp.json()["namespaces"] == ["default"]

    def test_save_chat(self, client, mock_state, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "ai_assistant.features.rag.handlers.DOCUMENTS_ROOT", tmp_path
        )
        mock_state.chunker.chunk = AsyncMock(return_value=[])
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_state.vector_store.add = AsyncMock(return_value=None)
        mock_state.vector_store.save = AsyncMock(return_value=None)

        resp = client.post(
            "/api/v1/rag/save-chat",
            json={
                "filename": "chat_test.md",
                "content": "## User\nHello\n\n---\n\n## Assistant\nHi!",
                "namespace": "personal",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert data["namespace"] == "personal"
        assert (tmp_path / "personal" / "chat_test.md").exists()

    def test_save_chat_invalid_namespace(self, client):
        resp = client.post(
            "/api/v1/rag/save-chat",
            json={
                "filename": "test.md",
                "content": "test",
                "namespace": "Invalid123",
            },
        )
        assert resp.status_code == 422
        # Pydantic 422: detail is a list of validation errors
        errors = resp.json()["detail"]
        assert isinstance(errors, list)
        assert any(e.get("loc") == ["body", "namespace"] for e in errors)

    def test_save_chat_default_namespace(
        self, client, mock_state, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "ai_assistant.features.rag.handlers.DOCUMENTS_ROOT", tmp_path
        )
        mock_state.chunker.chunk = AsyncMock(return_value=[])
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_state.vector_store.add = AsyncMock(return_value=None)
        mock_state.vector_store.save = AsyncMock(return_value=None)

        resp = client.post(
            "/api/v1/rag/save-chat",
            json={"filename": "chat.md", "content": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["namespace"] == "personal"

    def test_reindex_returns_started_immediately(self, client, tmp_path, monkeypatch):
        """POST /api/v1/rag/reindex returns task_id immediately without blocking."""
        from ai_assistant.features.rag import indexing as indexing_module

        monkeypatch.setattr(indexing_module, "DOCUMENTS_ROOT", tmp_path)
        (tmp_path / "personal").mkdir()
        (tmp_path / "personal" / "test.md").write_text("hello world")

        resp = client.post(
            "/api/v1/rag/reindex", json={"folder": "personal", "clear": False}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert "task_id" in data

    def test_reindex_status_unknown_task(self, client):
        resp = client.get("/api/v1/rag/reindex/status/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unknown"
        assert data["task_id"] == "nonexistent"

    def test_reindex_status_running(self, client, tmp_path, monkeypatch):
        from ai_assistant.features.rag import handlers as handlers_module
        from ai_assistant.features.rag import indexing as indexing_module

        monkeypatch.setattr(indexing_module, "DOCUMENTS_ROOT", tmp_path)
        (tmp_path / "personal").mkdir()
        (tmp_path / "personal" / "test.md").write_text("hello world")

        # Ensure semaphore is free for this test
        original_sem = handlers_module._reindex_semaphore
        handlers_module._reindex_semaphore = asyncio.Semaphore(1)

        try:
            resp = client.post(
                "/api/v1/rag/reindex", json={"folder": "personal", "clear": False}
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            # Poll until finished (with mocks it's near-instant)
            for _ in range(100):
                status_resp = client.get(f"/api/v1/rag/reindex/status/{task_id}")
                status_data = status_resp.json()
                if status_data["status"] in ("completed", "failed"):
                    break
            else:
                pytest.fail("Background reindex did not finish in time")

            assert status_data["task_id"] == task_id
            # Memory-leak guard: task must be removed from _reindex_tasks
            assert task_id not in handlers_module._reindex_tasks
        finally:
            handlers_module._reindex_semaphore = original_sem


class TestRAGQueryOffline:
    """POST /api/v1/rag/query — per-namespace config overrides."""

    def test_query_uses_per_namespace_prompt_and_threshold(self, client, mock_state):
        from unittest.mock import AsyncMock, patch

        with patch("ai_assistant.features.rag.handlers.RAGManager") as mock_mgr_cls:
            instance = mock_mgr_cls.return_value
            instance.query = AsyncMock(return_value={
                "answer": "test answer",
                "sources": [],
                "chunks_used": 0,
                "errors": [],
            })
            mock_state.config.namespaces = {
                "work": NamespaceConfig(threshold=0.3, chunk_size=1024, prompt="rag_creative"),
            }

            resp = client.post(
                "/api/v1/rag/query",
                json={"query": "test", "namespace": "work"},
            )
            assert resp.status_code == 200
            instance.query.assert_awaited_once()
            kwargs = instance.query.call_args.kwargs
            assert kwargs["relevance_threshold"] == 0.3
            assert kwargs["prompt_name"] == "rag_creative"
            assert kwargs["namespace"] == "work"


class TestChatPromptVersion:
    """Chat RAG must use the prompt version injected from config."""

    def test_chat_manager_uses_config_prompt_version(self, mock_state):
        """ChatManager must store and use the version passed from AppConfig."""
        from ai_assistant.features.chat.manager import ChatManager

        mgr = ChatManager(
            llm=mock_state.llm,
            prompt_version=mock_state.config.rag.prompt_version,
        )
        assert mgr.prompt_version == mock_state.config.rag.prompt_version

        # Verify override works
        mgr_v2 = ChatManager(
            llm=mock_state.llm,
            prompt_version="v2",
        )
        assert mgr_v2.prompt_version == "v2"


class TestCORSOffline:
    """CORS headers for browser extensions."""

    def test_preflight_headers(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    def test_actual_request_headers(self, client):
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
        # CORS middleware may add different headers depending on config
        assert any(
            h in resp.headers
            for h in ("access-control-allow-origin", "access-control-allow-credentials")
        )


# ── Online Tests (real server) ──


@pytest.mark.online
class TestHealthOnline:
    """Real server health check."""

    def test_server_responds(self, httpx_client):
        resp = httpx_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.online
class TestModelsOnline:
    """Real /v1/models endpoint."""

    def test_returns_model_list(self, httpx_client):
        resp = httpx_client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        assert all("id" in m for m in data["data"])


def _is_llm_server_available() -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 8080), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.mark.online
class TestChatOnline:
    """Real chat with running LLM."""

    @pytest.mark.skipif(
        not _is_llm_server_available(),
        reason="LLM server (port 8080) not available",
    )
    def test_non_streaming_chat(self, httpx_client):
        resp = httpx_client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [
                    {"role": "user", "content": "Say 'test' and nothing else"}
                ],
                "stream": False,
                "max_tokens": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] != ""
        assert data["choices"][0]["finish_reason"] in ["stop", "length"]

    @pytest.mark.skipif(
        not _is_llm_server_available(),
        reason="LLM server (port 8080) not available",
    )
    def test_streaming_chat(self, httpx_client):
        resp = httpx_client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
                "max_tokens": 5,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        text = resp.text
        assert "data:" in text
        assert "[DONE]" in text


@pytest.mark.online
class TestRAGOnline:
    """Real RAG with running pipeline."""

    def test_health_reports_status(self, httpx_client):
        resp = httpx_client.get("/api/v1/rag/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "index_loaded" in data
        assert "embedder_dim" in data

    def test_namespaces_list(self, httpx_client):
        resp = httpx_client.get("/api/v1/rag/namespaces")
        assert resp.status_code == 200
        assert isinstance(resp.json()["namespaces"], list)


@pytest.mark.online
class TestAdminOnline:
    """Real admin endpoints with running server."""

    def test_current_model(self, httpx_client):
        resp = httpx_client.get("/api/v1/admin/current-model")
        assert resp.status_code == 200
        data = resp.json()
        assert "model" in data
        assert "provider" in data


def test_main_import_does_not_trigger_load_config(monkeypatch):
    """Phase 4.4: importing main.py must not call load_config at module level."""
    import sys

    import ai_assistant.core.config

    call_count = 0

    def counting_load_config(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return ai_assistant.core.config.AppConfig()

    monkeypatch.setattr(ai_assistant.core.config, "load_config", counting_load_config)

    # Выгоняем ТОЛЬКО main.py — api.* и core.config оставляем в кэше,
    # иначе monkeypatch'и security/deps слетают для следующих тестов.
    removed = {}
    for key in list(sys.modules):
        if key == "ai_assistant.main" or key.startswith("ai_assistant.main."):
            removed[key] = sys.modules.pop(key, None)

    try:
        import ai_assistant.main

        assert call_count == 0, (
            f"load_config was called {call_count} time(s) during import of main.py. "
            "Module-level config loading is forbidden after phase 4.4."
        )
    finally:
        for key, mod in removed.items():
            if mod is not None:
                sys.modules[key] = mod


def test_lifespan_reconfigures_middleware_and_mounts_static(client):
    """Lifespan should reconfigure CORS from config and attempt static mount."""
    app = client.app

    # client fixture запустил lifespan → config должен быть в state
    assert hasattr(app.state, "config")
    assert isinstance(app.state.config, AppConfig)

    # Only CORSMiddleware remains after security layer simplification
    middleware_names = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in middleware_names


def test_middleware_present_at_import_time():
    """Middleware must be registered when main.py is imported, without loadConfig."""
    from ai_assistant.main import create_app

    app = create_app(lifespan=None)
    middleware_names = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in middleware_names


# ── Reindex status TTL / cap tests ──

@pytest.fixture(autouse=True)
def _clear_reindex_status():
    """Clear global _reindex_status before/after each test."""
    from ai_assistant.features.rag import handlers as rag_handlers

    rag_handlers._reindex_status.clear()
    yield
    rag_handlers._reindex_status.clear()


async def test_reindex_status_ttl_cleanup():
    """Expired entries are removed based on TTL; fresh entries survive."""
    from ai_assistant.features.rag import handlers as rag_handlers

    now = time.time()
    rag_handlers._reindex_status["old"] = {
        "status": "completed",
        "started_at": now - rag_handlers._REINDEX_STATUS_TTL_SECONDS - 100,
        "finished_at": now - rag_handlers._REINDEX_STATUS_TTL_SECONDS - 50,
    }
    rag_handlers._reindex_status["fresh"] = {
        "status": "running",
        "started_at": now - 10,
    }

    await rag_handlers._cleanup_reindex_status()

    assert "old" not in rag_handlers._reindex_status
    assert "fresh" in rag_handlers._reindex_status


async def test_reindex_status_cap_removes_oldest():
    """When over max entries, oldest by started_at are removed."""
    from ai_assistant.features.rag import handlers as rag_handlers

    now = time.time()
    max_entries = rag_handlers._REINDEX_STATUS_MAX_ENTRIES

    for i in range(max_entries + 2):
        rag_handlers._reindex_status[f"task-{i}"] = {
            "status": "completed",
            "started_at": now - (max_entries + 2 - i),
            "finished_at": now,
        }

    await rag_handlers._cleanup_reindex_status()

    assert len(rag_handlers._reindex_status) == max_entries
    assert "task-0" not in rag_handlers._reindex_status
    assert "task-1" not in rag_handlers._reindex_status
    assert f"task-{max_entries + 1}" in rag_handlers._reindex_status


async def test_reindex_status_cap_does_not_remove_running_if_under_cap():
    """Running tasks are not removed when total count is under the cap."""
    from ai_assistant.features.rag import handlers as rag_handlers

    now = time.time()
    rag_handlers._reindex_status["running"] = {
        "status": "running",
        "started_at": now - 100,
    }

    await rag_handlers._cleanup_reindex_status()

    assert "running" in rag_handlers._reindex_status


async def test_reindex_status_endpoint_returns_unknown_after_ttl(client):
    """E2E: after TTL cleanup, polling an expired task returns 'unknown'."""
    from ai_assistant.features.rag import handlers as rag_handlers

    with patch.object(rag_handlers, "_REINDEX_STATUS_TTL_SECONDS", 1):
        resp = client.post("/api/v1/rag/reindex", json={"folder": "__nonexistent__"})
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        await asyncio.sleep(1.5)

        status_resp = client.get(f"/api/v1/rag/reindex/status/{task_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "unknown"
