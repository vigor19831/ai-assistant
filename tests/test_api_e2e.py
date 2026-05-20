"""End-to-end API tests — works both offline (TestClient) and online (real server).

Offline: mocked state via TestClient — 100% reliable, no server needed.
Online: real HTTP calls when server detected — validates actual deployment.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch as mock_patch

import pytest

from core.domain.documents import Chunk, ChunkMetadata
from core.pipeline import RAGPipeline
from pipeline.steps import build_context, embed_query, generate, retrieve

# ── Offline Tests (TestClient) ──


class TestHealthOffline:
    """GET /health — always available, no deps."""

    def test_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "ai-assistant"

    def test_unauthorized_access(self, client, monkeypatch):
        """When API key is configured, unauthorized requests should fail."""
        monkeypatch.setattr("api.security.get_expected_api_key", lambda: "real-key")
        resp = client.post(
            "/chat",
            json={"message": "test"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status_code == 401

    def test_rate_limit_exceeded(self, client, monkeypatch):
        """When rate limiter blocks IP, should return 429."""
        monkeypatch.setattr("api.security.limiter.is_allowed", lambda ip: False)
        resp = client.post("/chat", json={"message": "test"})
        assert resp.status_code == 429


class TestInfoOffline:
    """GET /info — model badge for UI."""

    def test_openai_compatible_model_name(self, client, mock_state):
        mock_state.config.llm.provider = "openai_compatible"
        mock_state.config.llm.model = "gemma3:4b"
        resp = client.get("/info")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "openai_compatible"
        assert resp.json()["model"] == "gemma3:4b"

    def test_mock_provider(self, client, mock_state):
        mock_state.config.llm.provider = "mock"
        resp = client.get("/info")
        assert resp.status_code == 200
        assert resp.json()["model"] == "mock"

    def test_unknown_provider(self, client, mock_state):
        mock_state.config.llm.provider = "custom"
        resp = client.get("/info")
        assert resp.status_code == 200
        assert resp.json()["provider"] == "custom"
        assert resp.json()["model"] == "custom"

    def test_runtime_error_fallback(self, client):
        from api.deps import get_state
        from main import app

        original_override = app.dependency_overrides.get(get_state, None)

        def raise_runtime_error():
            raise RuntimeError("No app state available")

        try:
            app.dependency_overrides[get_state] = raise_runtime_error
            resp = client.get("/info")
            assert resp.status_code == 200
            assert resp.json() == {"provider": "unknown", "model": "unknown"}
        finally:
            if original_override is not None:
                app.dependency_overrides[get_state] = original_override
            else:
                app.dependency_overrides.pop(get_state, None)


class TestChatOffline:
    """POST /chat and /chat/stream — full chat feature."""

    def test_text_only(self, client):
        resp = client.post(
            "/chat", json={"message": "Hello", "conversation_id": "test-123"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["conversation_id"] == "test-123"
        assert data["role"] == "assistant"

    def test_generates_conversation_id(self, client):
        resp = client.post("/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        assert resp.json()["conversation_id"]  # auto-generated UUID

    def test_empty_message(self, client):
        """Empty message should still return 200 (handled by manager)."""
        resp = client.post("/chat", json={"message": " ", "conversation_id": "test"})
        assert resp.status_code == 200

    def test_with_image_base64(self, client):
        resp = client.post(
            "/chat",
            json={
                "message": "Describe this",
                "conversation_id": "test",
                "image_base64": "iVBORw0KGgo=",
            },
        )
        assert resp.status_code == 200

    def test_with_image_url(self, client):
        resp = client.post(
            "/chat",
            json={
                "message": "Describe this",
                "conversation_id": "test",
                "image_url": "http://example.com/img.png",
            },
        )
        assert resp.status_code == 200

    def test_with_voice(self, client, mock_state):
        import base64

        mock_state.voice_recognizer = MagicMock()
        mock_state.voice_recognizer.transcribe = AsyncMock(
            return_value="transcribed voice"
        )

        audio = base64.b64encode(b"fake_audio").decode()
        resp = client.post(
            "/chat",
            json={
                "message": "ignored",
                "conversation_id": "test",
                "voice_base64": audio,
            },
        )
        assert resp.status_code == 200
        mock_state.voice_recognizer.transcribe.assert_awaited_once()

    def test_stream_returns_sse(self, client):
        resp = client.post(
            "/chat/stream",
            json={"message": "Hello", "conversation_id": "test"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        text = resp.text
        assert "data: " in text
        assert "[DONE]" in text

    def test_stream_with_image(self, client):
        resp = client.post(
            "/chat/stream",
            json={
                "message": "Describe",
                "conversation_id": "test",
                "image_base64": "iVBORw0KGgo=",
            },
        )
        assert resp.status_code == 200
        assert "data:" in resp.text


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


class TestRAGOffline:
    """POST /rag/* — indexing, query, delete, health, namespaces."""

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
            "/rag/index",
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
            "/rag/index",
            json={
                "documents": [{"id": "d1", "content": "", "metadata": {}}],
                "namespace": "test",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["indexed_count"] == 0
        assert len(resp.json()["errors"]) > 0

    def test_query_rag(self, client, mock_state):
        import functools

        llm = MagicMock()
        llm.complete = AsyncMock(return_value=MagicMock(text="integrated answer"))
        step_funcs = [
            functools.partial(embed_query, embedder=mock_state.embedder),
            functools.partial(retrieve, vector_store=mock_state.vector_store),
            build_context,
            functools.partial(generate, llm=llm),
        ]
        mock_state.pipeline = RAGPipeline(step_funcs)
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        mock_state.vector_store.search = AsyncMock(
            return_value=[
                Chunk(
                    id="c1",
                    text="chunk1",
                    metadata=ChunkMetadata(source="d1", index=0, total_chunks=1),
                )
            ]
        )

        resp = client.post("/rag/query", json={"query": "hello?", "namespace": "work"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "integrated answer"
        assert data["chunks_used"] == 1
        assert len(data["sources"]) == 1

    def test_query_no_results(self, client, mock_state):
        import functools

        llm = MagicMock()
        llm.complete = AsyncMock(return_value=MagicMock(text="No info"))
        step_funcs = [
            functools.partial(embed_query, embedder=mock_state.embedder),
            functools.partial(retrieve, vector_store=mock_state.vector_store),
            build_context,
            functools.partial(generate, llm=llm),
        ]
        mock_state.pipeline = RAGPipeline(step_funcs)
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        mock_state.vector_store.search = AsyncMock(return_value=[])

        resp = client.post("/rag/query", json={"query": "unknown?"})
        assert resp.status_code == 200
        assert resp.json()["chunks_used"] == 0

    def test_delete_chunks(self, client, mock_state):
        mock_state.vector_store.delete = AsyncMock(return_value=None)
        resp = client.post(
            "/rag/delete", json={"chunk_ids": ["c1"], "namespace": "test"}
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_chunks"] == 1

    def test_delete_by_document_ids(self, client, mock_state):
        mock_state.vector_store.list_by_filter = AsyncMock(
            return_value=[("c1", {"source": "d1"})]
        )
        mock_state.vector_store.delete = AsyncMock(return_value=None)
        resp = client.post(
            "/rag/delete",
            json={"document_ids": ["d1"], "namespace": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_chunks"] == 1

    def test_health(self, client, mock_state):
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["default"])
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[("c1", {})])
        mock_state.embedder.dimension = 384
        resp = client.get("/rag/health")
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
        resp = client.get("/rag/namespaces")
        assert resp.status_code == 200
        assert "personal" in resp.json()["namespaces"]
        assert "work" in resp.json()["namespaces"]

    def test_list_namespaces_empty_fallback(self, client, mock_state):
        mock_state.config.vector_store.index_path = None
        resp = client.get("/rag/namespaces")
        assert resp.status_code == 200
        assert resp.json()["namespaces"] == ["default"]

    def test_save_chat(self, client, mock_state, tmp_path, monkeypatch):
        monkeypatch.setattr("features.rag.handlers.DOCUMENTS_ROOT", tmp_path)
        mock_state.chunker.chunk = AsyncMock(return_value=[])
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_state.vector_store.add = AsyncMock(return_value=None)
        mock_state.vector_store.save = AsyncMock(return_value=None)

        resp = client.post(
            "/rag/save-chat",
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
            "/rag/save-chat",
            json={
                "filename": "test.md",
                "content": "test",
                "namespace": "invalid",
            },
        )
        assert resp.status_code == 400
        assert "Invalid namespace" in resp.json()["detail"]

    def test_save_chat_default_namespace(
        self, client, mock_state, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("features.rag.handlers.DOCUMENTS_ROOT", tmp_path)
        mock_state.chunker.chunk = AsyncMock(return_value=[])
        mock_state.embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_state.vector_store.add = AsyncMock(return_value=None)
        mock_state.vector_store.save = AsyncMock(return_value=None)

        resp = client.post(
            "/rag/save-chat",
            json={"filename": "chat.md", "content": "test"},
        )
        assert resp.status_code == 200
        assert resp.json()["namespace"] == "personal"

    def test_reindex(self, client, tmp_path):
        async def fake_subprocess(*cmd, **kwargs):
            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(
                return_value=(
                    b"[personal] Done: 3 docs, 15 chunks\n"
                    b"[work] Done: 2 docs, 8 chunks",
                    b"",
                )
            )
            mock_proc.returncode = 0
            return mock_proc

        with mock_patch("asyncio.create_subprocess_exec", side_effect=fake_subprocess):
            resp = client.post(
                "/rag/reindex",
                json={"folder": "personal", "clear": True},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "personal" in data["results"]
        assert data["results"]["personal"]["indexed"] == 3
        assert data["results"]["personal"]["chunks"] == 15

    def test_reindex_script_not_found(self, client, tmp_path):
        class _MockPath:
            def __init__(self, *args):
                self._path = str(args[0]) if args else ""

            def exists(self):
                return False

            def __truediv__(self, other):
                return _MockPath(self._path + "/" + str(other))

            def __str__(self):
                return self._path

            @property
            def parent(self):
                return _MockPath(self._path)

        with mock_patch("features.rag.handlers.Path", _MockPath):
            resp = client.post("/rag/reindex", json={})
        assert resp.status_code == 500
        assert "not found" in resp.json()["detail"].lower()


class TestImageAnalysisOffline:
    """POST /image/analyze — vision feature."""

    def test_analyze_with_base64(self, client, mock_state):
        mock_state.vision = MagicMock()
        mock_state.vision.describe = AsyncMock(return_value="An image of a cat")
        resp = client.post(
            "/image/analyze",
            json={
                "image_base64": "abc123",
                "prompt": "What is this?",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "An image of a cat"

    def test_analyze_with_url(self, client, mock_state):
        mock_state.vision = MagicMock()
        mock_state.vision.describe = AsyncMock(return_value="An image")
        resp = client.post(
            "/image/analyze",
            json={
                "image_url": "http://example.com/img.png",
            },
        )
        assert resp.status_code == 200

    def test_analyze_no_image_raises_400(self, client):
        resp = client.post("/image/analyze", json={"prompt": "test"})
        assert resp.status_code == 400
        assert "image_base64 or image_url" in resp.json()["detail"]

    def test_analyze_fallback_to_llm(self, client, mock_state):
        """When vision adapter is None but LLM available, use LLM vision."""
        mock_state.vision = None
        mock_state.llm.complete = AsyncMock(
            return_value=MagicMock(text="LLM vision result")
        )
        resp = client.post(
            "/image/analyze",
            json={"image_base64": "abc", "prompt": "Describe"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "LLM vision result"


class TestCORSOffline:
    """CORS headers for browser extensions."""

    def test_preflight_headers(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    def test_actual_request_headers(self, client):
        resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in resp.headers


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


@pytest.mark.online
class TestChatOnline:
    """Real chat with running LLM."""

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
        resp = httpx_client.get("/rag/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "index_loaded" in data
        assert "embedder_dim" in data

    def test_namespaces_list(self, httpx_client):
        resp = httpx_client.get("/rag/namespaces")
        assert resp.status_code == 200
        assert isinstance(resp.json()["namespaces"], list)


@pytest.mark.online
class TestAdminOnline:
    """Real admin endpoints with running server."""

    def test_current_model(self, httpx_client):
        resp = httpx_client.get("/admin/current-model")
        assert resp.status_code == 200
        data = resp.json()
        assert "model" in data
        assert "provider" in data
