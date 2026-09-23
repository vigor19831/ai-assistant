"""E2E tests for AI Assistant API.

Given: FastAPI application with all routers assembled.
When: tests run via TestClient (offline) or real HTTP (online).
Then: all critical user flows are validated end-to-end.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assistant.core.config import NamespaceConfig
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import LLM_UNAVAILABLE, AdapterError

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
            json={"message": "  ", "conversation_id": "test"},
        )
        assert resp.status_code == 200

    def test_chat_llm_adapter_error_returns_503(self, mock_state, make_test_client):
        """Given: ChatManager.chat raises AdapterError.
        When: POST /api/v1/chat.
        Then: returns 503 Service Unavailable."""

        # Create a mock ChatManager that raises AdapterError
        mock_mgr = MagicMock()
        mock_mgr.chat = AsyncMock(side_effect=AdapterError("LLM down"))

        # Build app with dependency override
        test_client = make_test_client(mock_state, manager=mock_mgr)
        resp = test_client.post(
            "/api/v1/chat",
            json={"message": "Hello", "conversation_id": "test-503"},
        )
        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_chat_llm_generic_exception_returns_500(
        self, mock_state, make_test_client
    ):
        """Given: ChatManager.chat raises generic Exception.
        When: POST /api/v1/chat.
        Then: handler catches it and returns 500."""
        mock_mgr = MagicMock()
        mock_mgr.chat = AsyncMock(side_effect=Exception("Generic LLM fail"))

        test_client = make_test_client(
            mock_state, manager=mock_mgr, raise_server_exceptions=False
        )
        resp = test_client.post(
            "/api/v1/chat",
            json={"message": "Hello", "conversation_id": "test-500-generic"},
        )
        assert resp.status_code == 500
        assert "Internal server error" in resp.json()["detail"]


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

    def test_stream_trace_id_propagation(self, mock_state, make_test_client):
        """Given: handler generates trace_id for each request.
        When: POST /api/v1/chat/stream.
        Then: trace_id is passed to chat_manager via metadata."""

        captured_meta: dict[str, Any] = {}

        async def capture_stream(*args, **kwargs):
            captured_meta["metadata"] = kwargs.get("metadata", {})
            yield "chunk"

        mock_mgr = MagicMock()
        mock_mgr.stream_chat = capture_stream

        test_client = make_test_client(mock_state, manager=mock_mgr)
        resp = test_client.post(
            "/api/v1/chat/stream",
            json={"message": "Hello", "conversation_id": "test-trace"},
        )
        assert resp.status_code == 200
        assert "trace_id" in captured_meta.get("metadata", {})

    def test_stream_chat_llm_adapter_error_returns_sse_error(
        self, mock_state, make_test_client
    ):
        """Given: ChatManager.stream_chat raises AdapterError.
        When: POST /api/v1/chat/stream.
        Then: returns SSE stream with error payload and [DONE] sentinel."""

        async def failing_stream(*args, **kwargs):
            raise AdapterError("LLM stream down")
            yield ""

        mock_mgr = MagicMock()
        mock_mgr.stream_chat = failing_stream

        test_client = make_test_client(mock_state, manager=mock_mgr)
        resp = test_client.post(
            "/api/v1/chat/stream",
            json={"message": "Hello", "conversation_id": "test-stream-err"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "LLM service temporarily unavailable" in resp.text
        assert "data: [DONE]" in resp.text

    def test_stream_chat_generic_exception_returns_sse_error(
        self, mock_state, make_test_client
    ):
        """Given: ChatManager.stream_chat raises generic Exception.
        When: POST /api/v1/chat/stream.
        Then: returns SSE stream with error payload and [DONE] sentinel."""

        async def failing_stream(*args, **kwargs):
            raise Exception("Generic stream fail")
            yield ""

        mock_mgr = MagicMock()
        mock_mgr.stream_chat = failing_stream

        test_client = make_test_client(mock_state, manager=mock_mgr)
        resp = test_client.post(
            "/api/v1/chat/stream",
            json={"message": "Hello", "conversation_id": "test-stream-err-generic"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "Internal server error" in resp.text
        assert "data: [DONE]" in resp.text

    def test_stream_interruption_by_client(self, mock_state, make_test_client):
        """Given: server is producing an SSE stream.
        When: client disconnects after reading a few chunks.
        Then: handler does not crash; cancellation is handled gracefully."""

        async def endless_stream(*args, **kwargs):
            """Yield chunks immediately; client disconnects mid-stream."""
            for i in range(100):
                yield f"chunk {i}"
                # yield in async generator already yields control to event loop

        mock_mgr = MagicMock()
        mock_mgr.stream_chat = endless_stream

        test_client = make_test_client(mock_state, manager=mock_mgr)
        with test_client.stream(
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

    def test_stream_malformed_sse_handling(self, mock_state, make_test_client):
        """Given: stream raises exception containing quotes and newlines.
        When: POST /api/v1/chat/stream.
        Then: SSE error payload is valid JSON without injection."""

        async def _malicious_stream(*args, **kwargs):
            raise ValueError('Error with "quotes" and \n newlines')
            yield ""

        mock_mgr = MagicMock()
        mock_mgr.stream_chat = _malicious_stream

        test_client = make_test_client(mock_state, manager=mock_mgr)
        resp = test_client.post(
            "/api/v1/chat/stream",
            json={"message": 'test "quoted" and newline'},
        )
        assert resp.status_code == 200

        lines = [line for line in resp.text.splitlines() if line.startswith("data:")]
        assert len(lines) >= 1
        for line in lines:
            payload = line.removeprefix("data:").strip()
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
                "messages": [{"role": "user", "content": "    "}],
                "stream": False,
            },
        )
        assert resp.status_code == 400
        assert "non-empty content" in resp.json()["detail"]

    def test_openai_chat_completions_llm_error_returns_503(
        self, mock_state, make_test_client
    ):
        """Given: ChatManager.chat raises AdapterError in OAI endpoint.
        When: POST /v1/chat/completions.
        Then: returns 503 Service Unavailable."""

        mock_mgr = MagicMock()
        mock_mgr.chat = AsyncMock(side_effect=AdapterError("LLM down"))

        test_client = make_test_client(mock_state, manager=mock_mgr)
        resp = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "local",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert resp.status_code == 503

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

    def test_chat_completions_trace_id(self, mock_state, make_test_client):
        """Given: OpenAI handler generates trace_id.
        When: POST /v1/chat/completions (non-streaming).
        Then: trace_id is propagated to chat_manager metadata."""

        captured_meta: dict[str, Any] = {}

        async def capture_chat(*args, **kwargs):
            captured_meta["metadata"] = kwargs.get("metadata", {})
            return MagicMock(text="OK", metadata={}, tool_calls=[])

        mock_mgr = MagicMock()
        mock_mgr.chat = capture_chat

        test_client = make_test_client(mock_state, manager=mock_mgr)
        resp = test_client.post(
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

    def test_rag_index_embedder_error_returns_500(self, client_no_raise, mock_state):
        """Given: embedder.embed raises Exception during indexing.
        When: POST /api/v1/rag/index.
        Then: returns 500 Internal Server Error (unhandled in handler)."""
        mock_state.embedder.embed = AsyncMock(side_effect=Exception("Embedder down"))
        mock_state.chunker.chunk = AsyncMock(
            return_value=[
                Chunk(
                    id="c1",
                    text="test",
                    metadata=ChunkMetadata(source="s", index=0, total_chunks=1),
                )
            ]
        )

        resp = client_no_raise.post(
            "/api/v1/rag/index",
            json={
                "documents": [{"id": "d1", "content": "test", "metadata": {}}],
                "namespace": "test",
            },
        )
        assert resp.status_code == 500

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
        mock_state.embedder.dimension = 384
        resp = client.get("/api/v1/rag/health")
        assert resp.status_code == 200
        data = resp.json()
        # Endpoint returns "empty" when no chunks, "ok" when chunks exist
        assert data["status"] in ("ok", "empty")
        assert data["embedder_dim"] == 384

    def test_namespaces(self, client, mock_state, tmp_path, monkeypatch):
        """Given: index contains multiple namespaces.
        When: GET /api/v1/rag/namespaces.
        Then: returns list including those namespaces."""
        monkeypatch.setattr(mock_state.config.vector_store, "index_path", str(tmp_path))
        mock_state.vector_store.list_namespaces = AsyncMock(
            return_value=["test", "default"]
        )
        resp = client.get("/api/v1/rag/namespaces")
        assert resp.status_code == 200
        assert "test" in resp.json()["namespaces"]

    def test_save_chat(self, client, mock_state, tmp_path, monkeypatch):
        """Given: chat content to persist.
        When: POST /api/v1/rag/save-chat.
        Then: file is saved under namespace and indexing is attempted."""
        monkeypatch.setattr(mock_state.config.rag, "chat_exports_root", str(tmp_path))
        mock_state.chunker.chunk = AsyncMock(return_value=[])
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_state.vector_store.add = AsyncMock(return_value=None)
        mock_state.vector_store.save = AsyncMock(return_value=None)

        resp = client.post(
            "/api/v1/rag/save-chat",
            json={
                "filename": "chat_test.md",
                "content": "## User\nHello\n\n---\n\n## Assistant\nHi!",
                "namespace": "test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert data["namespace"] == "test"
        assert (tmp_path / "test" / "chat_test.md").exists()

    def test_reindex_validation(self, client):
        """Given: reindex payload has wrong types.
        When: POST /api/v1/rag/reindex.
        Then: returns 422 validation error pointing to the bad field."""
        resp = client.post(
            "/api/v1/rag/reindex",
            json={"target_namespace": 123, "clear": False},
        )
        assert resp.status_code == 422
        errors = resp.json()["detail"]
        assert isinstance(errors, list)
        assert any(e.get("loc") == ["body", "target_namespace"] for e in errors)

    def test_query_per_namespace_override(self, client, mock_state):
        """Given: namespace has custom prompt.
        When: POST /api/v1/rag/query with that namespace.
        Then: RAGManager receives overridden parameters."""
        mock_state.config.namespaces = {
            "test-alt": NamespaceConfig(chunk_size=1024, prompt="rag_creative"),
        }
        mock_state.rag_manager.query = AsyncMock(
            return_value={
                "answer": "test answer",
                "sources": [],
                "chunks_used": 0,
                "errors": [],
                "metrics": {
                    "chunks_used": 0,
                    "rerank_scores": [],
                    "context_tokens": 0,
                    "prompt_name": "rag_creative",
                    "pipeline_errors": [],
                    "duration_ms": 10,
                },
            }
        )

        resp = client.post(
            "/api/v1/rag/query",
            json={"query": "test", "namespace": "test-alt"},
        )
        assert resp.status_code == 200
        mock_state.rag_manager.query.assert_awaited_once()
        kwargs = mock_state.rag_manager.query.call_args.kwargs
        assert kwargs["prompt_name"] == "rag_creative"
        assert kwargs["namespace"] == "test-alt"

    def test_rag_query_llm_unavailable_returns_503(self, client, mock_state):
        """Given: RAG pipeline returns errors with empty answer.
        When: POST /api/v1/rag/query.
        Then: returns 503 Service Unavailable."""
        mock_state.rag_manager.query = AsyncMock(
            return_value={
                "answer": "",
                "sources": [],
                "chunks_used": 0,
                "errors": [f"{LLM_UNAVAILABLE} (LLM down)"],
                "metrics": {
                    "chunks_used": 0,
                    "rerank_scores": [],
                    "context_tokens": 0,
                    "prompt_name": "rag_strict",
                    "pipeline_errors": [f"{LLM_UNAVAILABLE} (LLM down)"],
                    "duration_ms": 10,
                },
            }
        )
        resp = client.post(
            "/api/v1/rag/query",
            json={"query": "test", "namespace": "default"},
        )
        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_rag_query_retrieve_error_returns_503(
        self, client_no_raise, mock_state
    ):
        """Given: vector_store.search raises Exception during query.
        When: POST /api/v1/rag/query.
        Then: pipeline catches it, returns 503 (errors + empty answer)."""
        mock_state.vector_store.search = AsyncMock(
            side_effect=Exception("Vector store down")
        )

        resp = client_no_raise.post(
            "/api/v1/rag/query",
            json={"query": "test", "namespace": "default"},
        )
        assert resp.status_code == 503

    def test_rag_query_reranker_error_returns_503(
        self, client_no_raise, mock_state
    ):
        """Given: reranker.rerank raises Exception during query.
        When: POST /api/v1/rag/query.
        Then: pipeline catches it, returns 503 (errors + empty answer)."""
        mock_state.vector_store.search = AsyncMock(
            return_value=[
                Chunk(
                    id="c1",
                    text="test chunk",
                    embedding=[0.1] * 384,
                    metadata=ChunkMetadata(source="s", index=0, total_chunks=1),
                )
            ]
        )
        mock_state.reranker.rerank = AsyncMock(side_effect=Exception("Reranker down"))

        resp = client_no_raise.post(
            "/api/v1/rag/query",
            json={"query": "test", "namespace": "default"},
        )
        assert resp.status_code == 503

    def test_query_empty_result_handling(self, client, mock_state):
        """Given: query yields no relevant chunks but no errors.
        When: POST /api/v1/rag/query.
        Then: response contains empty answer and zero chunks_used gracefully."""
        mock_state.rag_manager.query = AsyncMock(
            return_value={
                "answer": "No information available.",
                "sources": [],
                "chunks_used": 0,
                "errors": [],
                "metrics": {
                    "chunks_used": 0,
                    "rerank_scores": [],
                    "context_tokens": 0,
                    "prompt_name": "rag_strict",
                    "pipeline_errors": [],
                    "duration_ms": 10,
                },
            }
        )

        resp = client.post(
            "/api/v1/rag/query",
            json={"query": "nonexistent topic", "namespace": "default"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "No information available."
        assert data["chunks_used"] == 0


# ── Admin ──


@pytest.mark.slow
@pytest.mark.e2e
class TestE2EAdmin:
    """E2E tests for /admin/* endpoints."""

    def test_current_model_disabled_by_default(self, client, mock_state):
        """Given: admin_enabled is False (default).
        When: GET /admin/current-model.
        Then: returns 404."""
        mock_state.config.llm.model = "test-model"
        mock_state.config.llm.provider = "test-provider"
        resp = client.get("/admin/current-model")
        assert resp.status_code == 404

    def test_current_model_when_enabled(self, client, mock_state):
        """Given: admin_enabled is True.
        When: GET /admin/current-model.
        Then: returns both values."""
        mock_state.config.security.admin_enabled = True
        mock_state.config.llm.model = "test-model"
        mock_state.config.llm.provider = "test-provider"
        resp = client.get("/admin/current-model")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "test-model"
        assert data["provider"] == "test-provider"

    def test_update_key_when_enabled(self, client, mock_state, monkeypatch):
        """Given: admin_enabled is True and a new API key is provided.
        When: POST /admin/api-key.
        Then: key is updated with source 'runtime_override'."""
        mock_state.config.security.admin_enabled = True
        monkeypatch.setattr(
            "ai_assistant.api.security.get_expected_api_key", lambda: "old-key"
        )
        resp = client.post(
            "/admin/api-key",
            json={"api_key": "new-secret-key"},
            headers={"Authorization": "Bearer old-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] is True
        assert data["source"] == "runtime_override"

    def test_clear_key_when_enabled(self, client, mock_state):
        """Given: admin_enabled is True and admin wants to clear runtime API key.
        When: POST /admin/api-key with null.
        Then: key is cleared and source indicates env/none."""
        mock_state.config.security.admin_enabled = True
        resp = client.post(
            "/admin/api-key",
            json={"api_key": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] is True
        assert data["source"] == "env_var_fallback"

    def test_update_key_disabled_by_default(self, client):
        """Given: admin_enabled is False (default).
        When: POST /admin/api-key.
        Then: returns 404."""
        resp = client.post(
            "/admin/api-key",
            json={"api_key": "new-secret-key"},
        )
        assert resp.status_code == 404
