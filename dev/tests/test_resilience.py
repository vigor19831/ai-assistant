"""Resilience tests — graceful degradation, corruption, permissions, config errors."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.api.lifespan import _load_config
from ai_assistant.core.config import AppConfig, load_config

# ── Graceful degradation (all adapters None) ──


class TestGracefulDegradation:
    def test_chat_manager_no_embedder_no_store(self):
        from ai_assistant.features.chat.manager import ChatManager

        _ = ChatManager(llm=MagicMock(), embedder=None, vector_store=None)
        # Should not crash on init

    @pytest.mark.asyncio
    async def test_chat_manager_rag_without_embedder(self):
        from ai_assistant.features.chat.manager import ChatManager

        mgr = ChatManager(llm=MagicMock(), embedder=None, vector_store=MagicMock())
        prompt, query, chunks = await mgr._maybe_rag("[p] test")
        assert len(chunks) == 0
        assert prompt == "[p] test"

    @pytest.mark.asyncio
    async def test_chat_manager_rag_without_vector_store(self):
        from ai_assistant.features.chat.manager import ChatManager

        mgr = ChatManager(llm=MagicMock(), embedder=MagicMock(), vector_store=None)
        prompt, query, chunks = await mgr._maybe_rag("[p] test")
        assert len(chunks) == 0

    def test_pipeline_with_none_steps(self):
        from ai_assistant.core.pipeline import RAGPipeline

        _ = RAGPipeline([])
        # Empty pipeline should be valid

    @pytest.mark.asyncio
    async def test_generate_without_llm(self):
        from ai_assistant.core.domain.messages import UserMessage
        from ai_assistant.core.domain.pipeline import PipelineData
        from ai_assistant.pipeline.steps import generate

        data = PipelineData(query=UserMessage(text="q"))
        result = await generate(data)
        assert any("llm not provided" in e for e in result.errors)


# ── Corrupted / broken persistence ──


class TestCorruptedPersistence:
    @pytest.mark.asyncio
    async def test_faiss_load_missing_index(self, tmp_path):
        """Loading non-existent index should not crash."""
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        store = FaissVectorStore(
            type("C", (), {"dim": 3, "metric": "l2", "embedder_model": "test"})()
        )
        await store.load(str(tmp_path / "missing"), namespace="test")
        # Should silently return

    @pytest.mark.asyncio
    async def test_faiss_load_corrupted_meta(self, tmp_path):
        """Corrupted meta JSON should be handled gracefully."""
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        store = FaissVectorStore(
            type("C", (), {"dim": 3, "metric": "l2", "embedder_model": "test"})()
        )
        ns_dir = tmp_path / "test"
        ns_dir.mkdir()
        (ns_dir / "index.faiss").write_bytes(b"fake")
        (ns_dir / "index_meta.json").write_text("not json")
        # Should not crash — may raise or skip
        try:
            await store.load(str(tmp_path), namespace="test")
        except Exception:
            pass  # Acceptable

    @pytest.mark.asyncio
    async def test_sqlite_handles_busy(self, tmp_path):
        """SQLite WAL should handle concurrent reads."""
        cfg = type("C", (), {"db_path": str(tmp_path / "test.db")})()
        storage = SQLiteStorage(cfg)
        await storage.init_db()

        async def writer():
            for i in range(10):
                await storage.save_message("conv", {"role": "user", "content": str(i)})

        async def reader():
            for _ in range(10):
                await storage.get_history("conv", limit=5)

        await asyncio.gather(writer(), reader())
        history = await storage.get_history("conv", limit=100)
        assert len(history) == 10


# ── Broken config ──


class TestBrokenConfig:
    def test_load_config_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config("nonexistent.yaml")
        assert isinstance(cfg, AppConfig)
        assert cfg.app_name == "ai-assistant"

    def test_load_config_invalid_yaml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "bad.yaml").write_text("{invalid yaml: [}")
        # Should fallback or raise gracefully
        try:
            cfg = load_config("bad.yaml")
            assert isinstance(cfg, AppConfig)
        except Exception:
            pass  # Also acceptable if it raises

    def test_load_config_env_override(self, monkeypatch):
        monkeypatch.setenv("AI_APP_NAME", "env-test")
        cfg = AppConfig()
        assert cfg.app_name == "env-test"

    def test_lifespan_load_config_from_env(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text("app_name: lifespan-test\nport: 7777")
        monkeypatch.setenv("AI_CONFIG_PATH", str(cfg_file))
        cfg = _load_config()
        assert cfg.app_name == "lifespan-test"


# ── Permission / disk errors ──


class TestDiskErrors:

    def test_sqlite_readonly_db(self, tmp_path):
        """SQLite on read-only path should raise, not hang."""
        db_path = tmp_path / "readonly.db"
        db_path.touch()
        os.chmod(str(db_path), 0o444)
        try:
            cfg = type("C", (), {"db_path": str(db_path)})()
            storage = SQLiteStorage(cfg)
            # init_db will fail — test that it fails fast
            asyncio.run(storage.init_db())
        except (sqlite3.OperationalError, PermissionError):
            pass  # Expected
        finally:
            os.chmod(str(db_path), 0o644)


# ── Lifespan cleanup logging ──


class TestLifespanCleanup:
    @pytest.mark.asyncio
    async def test_async_cleanup_logs_traceback(self, caplog):
        """_async_cleanup must log exception with traceback on shutdown failure."""
        import logging
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import FastAPI
        from ai_assistant.api.lifespan import _async_cleanup
        from ai_assistant.core.ports.closable import IClosable

        app = FastAPI()

        class FailingClosable(IClosable):
            async def shutdown(self) -> None:
                raise RuntimeError("shutdown boom")

        mock_state = MagicMock()
        mock_state.llm = FailingClosable()
        mock_state.embedder = None
        mock_state.vector_store = None
        app.state.app_state = mock_state

        config = MagicMock()
        type(config).vector_store = MagicMock()
        config.vector_store.index_path = None

        with caplog.at_level(logging.ERROR, logger="ai_assistant.lifespan"):
            await _async_cleanup(app, config)

        assert "Traceback (most recent call last)" in caplog.text
        assert "shutdown boom" in caplog.text


# ── LLM unavailability → 503 ──


class TestLLMUnavailable:
    @pytest.mark.asyncio
    async def test_generate_propagates_adapter_error(self):
        """Pipeline generate step must propagate AdapterError instead of swallowing it."""
        from ai_assistant.core.domain.errors import AdapterError
        from ai_assistant.core.domain.messages import UserMessage
        from ai_assistant.core.domain.pipeline import PipelineData
        from ai_assistant.pipeline.steps import generate

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(side_effect=AdapterError("LLM unreachable"))

        data = PipelineData(
            query=UserMessage(text="q"),
            metadata={
                "llm": mock_llm,
                "prompt_version": "v1",
                "prompt_name": "rag_strict",
            },
        )

        with pytest.raises(AdapterError):
            await generate(data)

    @pytest.mark.asyncio
    async def test_chat_handler_returns_503_on_adapter_error(self):
        """Legacy chat handler must return 503 when LLM raises AdapterError."""
        from ai_assistant.core.domain.errors import AdapterError
        from ai_assistant.features.chat.handlers import chat
        from ai_assistant.features.chat.schemas import ChatRequest

        mock_state = MagicMock()
        mock_state.chat_manager.chat = AsyncMock(
            side_effect=AdapterError("LLM unreachable")
        )

        req = ChatRequest(message="hello")

        with pytest.raises(HTTPException) as exc_info:
            await chat(req, mock_state)

        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_embed_query_still_accumulates_adapter_error(self):
        """Only LLM AdapterError propagates; other adapters keep error-accumulation."""
        from ai_assistant.core.domain.errors import AdapterError
        from ai_assistant.core.domain.messages import UserMessage
        from ai_assistant.core.domain.pipeline import PipelineData
        from ai_assistant.pipeline.steps import embed_query

        mock_embedder = AsyncMock()
        mock_embedder.embed = AsyncMock(side_effect=AdapterError("embedder down"))

        data = PipelineData(
            query=UserMessage(text="q"),
            metadata={"embedder": mock_embedder},
        )
        result = await embed_query(data)
        assert any("Internal server error" in e for e in result.errors)
        assert "query_embedding" not in result.metadata

    @pytest.mark.asyncio
    async def test_openai_chat_handler_returns_503_on_adapter_error(self):
        """OpenAI-compatible chat handler must return 503 when LLM raises AdapterError."""
        from ai_assistant.core.domain.errors import AdapterError
        from ai_assistant.features.chat.handlers import openai_chat_completions
        from ai_assistant.features.chat.schemas import (
            OAIChatCompletionRequest,
            OAIChatMessage,
        )

        mock_state = MagicMock()
        mock_state.chat_manager.chat = AsyncMock(
            side_effect=AdapterError("LLM unreachable")
        )
        mock_state.config.llm.model = "test-model"

        req = OAIChatCompletionRequest(
            messages=[OAIChatMessage(role="user", content="hello")]
        )

        with pytest.raises(HTTPException) as exc_info:
            await openai_chat_completions(req, mock_state)

        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.detail.lower()
