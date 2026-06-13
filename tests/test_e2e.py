"""E2E tests for AI Assistant API.

Given: FastAPI application with all routers assembled.
When: tests run via TestClient (offline) or real HTTP (online).
Then: all critical user flows are validated end-to-end.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from ai_assistant.core.config import NamespaceConfig
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.logger import get_logger

logger = get_logger(__name__)


# ── Fixtures ──


@pytest.fixture
def client(mock_state):
    """Return a TestClient with mocked app state and auth header."""
    from ai_assistant.main import create_app
    from ai_assistant.api.security import set_api_key

    # Chat manager must return real objects for ChatResponse validation
    from ai_assistant.core.domain.messages import AssistantMessage
    mock_state.chat_manager.chat = AsyncMock(
        return_value=AssistantMessage(text="Hello!", metadata={"tokens": 2})
    )

    async def fake_stream(*args, **kwargs):
        yield "Hello"
        yield "!"

    mock_state.chat_manager.stream_chat = fake_stream

    set_api_key("test-e2e-key")

    app = create_app()
    app.state.app_state = mock_state
    return TestClient(app, headers={"Authorization": "Bearer test-e2e-key"})


# ── Health & Info ──

@pytest.mark.slow
@pytest.mark.e2e
class TestE2EHealth:
    """E2E tests for public health and info endpoints."""

    def test_health_returns_ok(self, client):
        """Given: application is running.
        When: GET /health is requested.
        Then: returns 200 with status ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_info_returns_provider_and_model(self, client, mock_state):
        """Given: LLM provider and model are configured.
        When: GET /info is requested.
        Then: returns correct provider and model names."""
        mock_state.config.llm.provider = "openai_compatible"
        mock_state.config.llm.model = "gemma3:4b"
        resp = client.get("/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["llm_provider"] == "openai_compatible"
        assert data["llm_model"] == "gemma3:4b"


# ── Legacy Chat ──

@pytest.mark.slow
@pytest.mark.e2e
class TestE2EChat:
    """E2E tests for legacy /api/v1/chat endpoints."""

    def test_chat_returns_text(self, client):
        """Given: user sends a text message.
        When: POST /api/v1/chat.
        Then: returns assistant response with message text."""
        resp = client.post(
            "/api/v1/chat",
            json={"message": "Hello", "conversation_id": "test-123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["conversation_id"] == "test-123"

    def test_chat_generates_conversation_id(self, client):
        """Given: user omits conversation_id.
        When: POST /api/v1/chat.
        Then: auto-generates a valid UUID conversation_id."""
        resp = client.post("/api/v1/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        assert resp.json()["conversation_id"]

    def test_chat_empty_message_returns_200(self, client):
        """Given: user sends whitespace-only message.
        When: POST /api/v1/chat.
        Then: returns 200 OK (schema accepts whitespace-only)."""
        resp = client.post(
            "/api/v1/chat",
            json={"message": " ", "conversation_id": "test"},
        )
        assert resp.status_code == 200

    def test_chat_prompt_version(self, mock_state):
        """Given: config specifies a RAG prompt version.
        When: ChatManager is instantiated.
        Then: it stores and exposes the configured prompt version."""
        from ai_assistant.adapters.reranker_null import NullReranker
        from ai_assistant.features.chat.manager import ChatManager

        reranker = NullReranker(None)
        mgr = ChatManager(
            llm=mock_state.llm,
            reranker=reranker,
            prompt_version=mock_state.config.rag.prompt_version,
        )
        assert mgr.prompt_version == mock_state.config.rag.prompt_version

        mgr_v2 = ChatManager(
            llm=mock_state.llm,
            reranker=reranker,
            prompt_version="v2",
        )
        assert mgr_v2.prompt_version == "v2"


# ── SSE Streaming ──

@pytest.mark.slow
@pytest.mark.e2e
class TestE2EStream:
    """E2E tests for /api/v1/chat/stream SSE endpoint."""

    def test_stream_sse_format(self, client):
        """Given: user requests streaming chat.
        When: POST /api/v1/chat/stream.
        Then: response has text/event-stream content type and data: lines."""
        resp = client.post(
            "/api/v1/chat/stream",
            json={"message": "Hello", "conversation_id": "test"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        assert "data:" in resp.text

    def test_stream_trace_id_propagation(self, client, mock_state):
        """Given: handler generates trace_id for each request.
        When: POST /api/v1/chat/stream.
        Then: trace_id is passed to chat_manager via metadata."""
        captured_meta: dict[str, Any] = {}

        async def capture_stream(*args, **kwargs):
            captured_meta["metadata"] = kwargs.get("metadata", {})
            yield "chunk"

        mock_state.chat_manager.stream_chat = capture_stream

        resp = client.post(
            "/api/v1/chat/stream",
            json={"message": "Hello", "conversation_id": "test-trace"},
        )
        assert resp.status_code == 200
        assert "trace_id" in captured_meta.get("metadata", {})

    def test_stream_interruption_by_client(self, client, mock_state):
        """Given: server is producing a slow SSE stream.
        When: client disconnects after reading a few chunks.
        Then: handler does not crash; cancellation is handled gracefully."""
        async def slow_stream(*args, **kwargs):
            for i in range(100):
                await asyncio.sleep(0.01)
                yield f"chunk {i}"

        mock_state.chat_manager.stream_chat = slow_stream

        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "Hello"},
        ) as resp:
            assert resp.status_code == 200
            # Read a few chunks then exit context to simulate disconnect
            chunks = []
            for chunk in resp.iter_text():
                chunks.append(chunk)
                if len(chunks) >= 3:
                    break
            assert len(chunks) >= 1

    def test_stream_malformed_sse_handling(self, client, mock_state):
        """Given: stream raises exception containing quotes and newlines.
        When: POST /api/v1/chat/stream.
        Then: SSE error payload is valid JSON without injection."""
        async def _malicious_stream(*args, **kwargs):
            raise ValueError('Error with "quotes" and \n newlines')
            yield ""  # noqa: B901 — forces async generator protocol

        mock_state.chat_manager.stream_chat = _malicious_stream

        resp = client.post(
            "/api/v1/chat/stream",
            json={"message": 'test "quoted" and newline'},
        )
        assert resp.status_code == 200

        lines = [line for line in resp.text.splitlines() if line.startswith("data:")]
        assert len(lines) >= 1
        for line in lines:
            payload = line.removeprefix("data: ").strip()
            if payload == "[DONE]":
                continue
            data = json.loads(payload)
            assert data.get("error") == "Internal server error"


# ── OpenAI Compatible ──

@pytest.mark.slow
@pytest.mark.e2e
class TestE2EOpenAICompat:
    """E2E tests for OpenAI-compatible /v1/* endpoints."""

    def test_list_models(self, client, mock_state):
        """Given: LLM models are configured.
        When: GET /v1/models.
        Then: returns a list of model objects with IDs."""
        mock_state.config.llm.available_models = ["model-a", "model-b"]
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 2
        assert all("id" in m for m in data["data"])

    def test_chat_completions_empty_user_message_returns_400(self, client):
        """Given: request has no user message with non-empty content.
        When: POST /v1/chat/completions.
        Then: returns 400 with clear error detail."""
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "system", "content": "test"}],
                "stream": False,
            },
        )
        assert resp.status_code == 400
        assert "non-empty content" in resp.json()["detail"]

    def test_chat_completions_whitespace_user_message_returns_400(self, client):
        """Given: user message is whitespace only.
        When: POST /v1/chat/completions.
        Then: returns 400 with clear error detail."""
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": "   "}],
                "stream": False,
            },
        )
        assert resp.status_code == 400
        assert "non-empty content" in resp.json()["detail"]

    def test_chat_completions_stream(self, client):
        """Given: stream=True is requested.
        When: POST /v1/chat/completions.
        Then: returns SSE stream with data: lines."""
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

    def test_chat_completions_trace_id(self, client, mock_state):
        """Given: OpenAI handler generates trace_id.
        When: POST /v1/chat/completions (non-streaming).
        Then: trace_id is propagated to chat_manager metadata."""
        captured_meta: dict[str, Any] = {}

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
        assert "trace_id" in captured_meta.get("metadata", {})


# ── RAG ──

@pytest.mark.slow
@pytest.mark.e2e
class TestE2ERAG:
    """E2E tests for /api/v1/rag/* endpoints."""

    def test_index_empty_content(self, client, mock_state):
        """Given: document has empty content.
        When: POST /api/v1/rag/index.
        Then: returns 0 indexed chunks and reports an error."""
        mock_state.chunker.chunk = AsyncMock(return_value=[])
        resp = client.post(
            "/api/v1/rag/index",
            json={
                "documents": [{"id": "d1", "content": "", "metadata": {}}],
                "namespace": "test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["indexed_count"] == 0
        assert len(data.get("errors", [])) > 0

    def test_delete_chunks(self, client, mock_state):
        """Given: chunks exist in a namespace.
        When: POST /api/v1/rag/delete with chunk_ids.
        Then: returns correct deleted_chunks count."""
        mock_state.vector_store.delete = AsyncMock(return_value=None)
        resp = client.post(
            "/api/v1/rag/delete",
            json={"chunk_ids": ["c1"], "namespace": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_chunks"] == 1

    def test_health(self, client, mock_state):
        """Given: RAG pipeline is initialized.
        When: GET /api/v1/rag/health.
        Then: returns status, index_loaded, and embedder_dim."""
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[("c1", {})])
        mock_state.vector_store.count = AsyncMock(return_value=5)
        mock_state.embedder.dimension = 384
        resp = client.get("/api/v1/rag/health")
        assert resp.status_code == 200
        data = resp.json()
        # Endpoint returns "empty" when no chunks, "ok" when chunks exist
        assert data["status"] in ("ok", "empty")
        assert data["embedder_dim"] == 384

    def test_namespaces(self, client, mock_state):
        """Given: index contains multiple namespaces.
        When: GET /api/v1/rag/namespaces.
        Then: returns list including those namespaces."""
        mock_state.config.vector_store.index_path = "./data/indices"
        mock_state.vector_store.list_namespaces = AsyncMock(
            return_value=["personal", "work"]
        )
        resp = client.get("/api/v1/rag/namespaces")
        assert resp.status_code == 200
        assert "personal" in resp.json()["namespaces"]

    def test_save_chat(self, client, mock_state, tmp_path, monkeypatch):
        """Given: chat content to persist.
        When: POST /api/v1/rag/save-chat.
        Then: file is saved under namespace and indexing is attempted."""
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

    def test_reindex_validation(self, client):
        """Given: reindex payload has wrong types.
        When: POST /api/v1/rag/reindex.
        Then: returns 422 validation error pointing to the bad field."""
        resp = client.post(
            "/api/v1/rag/reindex",
            json={"folder": 123, "clear": False},
        )
        assert resp.status_code == 422
        errors = resp.json()["detail"]
        assert isinstance(errors, list)
        assert any(e.get("loc") == ["body", "folder"] for e in errors)

    def test_reindex_status_polling(self, client, tmp_path, monkeypatch):
        """Given: reindex task is started.
        When: polling /api/v1/rag/reindex/status/{task_id}.
        Then: eventually reports completed and task is cleaned from memory."""
        from ai_assistant.features.rag import handlers as handlers_module
        from ai_assistant.features.rag import indexing as indexing_module

        monkeypatch.setattr(indexing_module, "DOCUMENTS_ROOT", tmp_path)
        (tmp_path / "personal").mkdir()
        (tmp_path / "personal" / "test.md").write_text("hello world")

        original_sem = handlers_module._reindex_semaphore
        handlers_module._reindex_semaphore = asyncio.Semaphore(1)

        try:
            resp = client.post(
                "/api/v1/rag/reindex", json={"folder": "personal", "clear": False}
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            for _ in range(100):
                status_resp = client.get(f"/api/v1/rag/reindex/status/{task_id}")
                status_data = status_resp.json()
                if status_data["status"] in ("completed", "failed"):
                    break
            else:
                pytest.fail("Background reindex did not finish in time")

            assert status_data["task_id"] == task_id
            assert task_id not in handlers_module._reindex_tasks
        finally:
            handlers_module._reindex_semaphore = original_sem

    def test_reindex_ttl_cleanup(self, client):
        """Given: a reindex task finishes and TTL passes.
        When: status endpoint is polled after TTL expiry.
        Then: expired task is removed and status returns 'unknown'."""
        from ai_assistant.features.rag import handlers as handlers_module

        with patch.object(handlers_module, "_REINDEX_STATUS_TTL_SECONDS", 1):
            resp = client.post(
                "/api/v1/rag/reindex", json={"folder": "__nonexistent__"}
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            time.sleep(1.5)

            status_resp = client.get(f"/api/v1/rag/reindex/status/{task_id}")
            assert status_resp.status_code == 200
            assert status_resp.json()["status"] == "unknown"

    def test_query_per_namespace_override(self, client, mock_state):
        """Given: namespace has custom prompt and relevance threshold.
        When: POST /api/v1/rag/query with that namespace.
        Then: RAGManager receives overridden parameters."""
        with patch("ai_assistant.features.rag.handlers.RAGManager") as mock_mgr_cls:
            instance = mock_mgr_cls.return_value
            instance.query = AsyncMock(
                return_value={
                    "answer": "test answer",
                    "sources": [],
                    "chunks_used": 0,
                    "errors": [],
                }
            )
            mock_state.config.namespaces = {
                "work": NamespaceConfig(
                    threshold=0.3, chunk_size=1024, prompt="rag_creative"
                ),
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

    def test_query_empty_result_handling(self, client, mock_state):
        """Given: query yields no relevant chunks.
        When: POST /api/v1/rag/query.
        Then: response contains empty answer and zero chunks_used gracefully."""
        with patch("ai_assistant.features.rag.handlers.RAGManager") as mock_mgr_cls:
            instance = mock_mgr_cls.return_value
            instance.query = AsyncMock(
                return_value={
                    "answer": "",
                    "sources": [],
                    "chunks_used": 0,
                    "errors": [],
                }
            )

            resp = client.post(
                "/api/v1/rag/query",
                json={"query": "nonexistent topic", "namespace": "default"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["answer"] == ""
            assert data["chunks_used"] == 0


# ── Admin ──

@pytest.mark.slow
@pytest.mark.e2e
class TestE2EAdmin:
    """E2E tests for /api/v1/admin/* endpoints."""

    def test_current_model(self, client, mock_state):
        """Given: LLM model and provider are configured.
        When: GET /api/v1/admin/current-model.
        Then: returns both values."""
        mock_state.config.llm.model = "test-model"
        mock_state.config.llm.provider = "test-provider"
        resp = client.get("/api/v1/admin/current-model")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "test-model"
        assert data["provider"] == "test-provider"

    def test_update_key(self, client, monkeypatch):
        """Given: a new API key is provided.
        When: POST /api/v1/admin/api-key.
        Then: key is updated with source 'runtime_override'."""
        monkeypatch.setattr(
            "ai_assistant.api.security.get_expected_api_key", lambda: "old-key"
        )
        # Use the current expected key for auth
        resp = client.post(
            "/api/v1/admin/api-key",
            json={"api_key": "new-secret-key"},
            headers={"Authorization": "Bearer old-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] is True
        assert data["source"] == "runtime_override"

    def test_clear_key(self, client):
        """Given: admin wants to clear runtime API key.
        When: POST /api/v1/admin/api-key with null.
        Then: key is cleared and source indicates env/none."""
        resp = client.post(
            "/api/v1/admin/api-key",
            json={"api_key": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] is True
        assert data["source"] == "env_var_or_none"
