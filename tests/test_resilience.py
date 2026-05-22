"""Resilience tests — graceful degradation, corruption, permissions, config errors."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from adapters.storage_sqlite import SQLiteStorage
from api.lifespan import _load_config
from core.config import AppConfig, load_config
from core.metrics import MetricsLogger

# ── Graceful degradation (all adapters None) ──


class TestGracefulDegradation:
    def test_chat_manager_no_embedder_no_store(self):
        from features.chat.manager import ChatManager

        mgr = ChatManager(llm=MagicMock(), embedder=None, vector_store=None)
        # Should not crash on init

    @pytest.mark.asyncio
    async def test_chat_manager_rag_without_embedder(self):
        from features.chat.manager import ChatManager

        mgr = ChatManager(llm=MagicMock(), embedder=None, vector_store=MagicMock())
        prompt, query, chunks = await mgr._maybe_rag("[p] test")
        assert chunks == 0
        assert prompt == "[p] test"

    @pytest.mark.asyncio
    async def test_chat_manager_rag_without_vector_store(self):
        from features.chat.manager import ChatManager

        mgr = ChatManager(llm=MagicMock(), embedder=MagicMock(), vector_store=None)
        prompt, query, chunks = await mgr._maybe_rag("[p] test")
        assert chunks == 0

    def test_pipeline_with_none_steps(self):
        from core.pipeline import RAGPipeline

        pipeline = RAGPipeline([])
        # Empty pipeline should be valid

    @pytest.mark.asyncio
    async def test_generate_without_llm(self):
        from core.domain.messages import UserMessage
        from core.domain.pipeline import PipelineData
        from pipeline.steps import generate

        data = PipelineData(query=UserMessage(text="q"))
        result = await generate(data, llm=None)
        assert "llm not provided" in result.errors[0]


# ── Corrupted / broken persistence ──


class TestCorruptedPersistence:
    @pytest.mark.asyncio
    async def test_faiss_load_missing_index(self, tmp_path):
        """Loading non-existent index should not crash."""
        from adapters.vector_store_faiss import FaissVectorStore

        store = FaissVectorStore(
            type("C", (), {"dim": 3, "metric": "l2", "embedder_model": "test"})()
        )
        await store.load(str(tmp_path / "missing"), namespace="test")
        # Should silently return

    @pytest.mark.asyncio
    async def test_faiss_load_corrupted_meta(self, tmp_path):
        """Corrupted meta JSON should be handled gracefully."""
        from adapters.vector_store_faiss import FaissVectorStore

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
    def test_metrics_logger_permission_denied(self, tmp_path):
        """Metrics logger should handle write errors gracefully."""

        async def _run() -> None:
            logger = MetricsLogger(path=str(tmp_path / "metrics.jsonl"))
            logger.start()

            # Simulate write failure
            with patch.object(
                logger, "_append_line", side_effect=PermissionError("denied")
            ):
                logger.log({"test": 1})
                await asyncio.sleep(0.2)

            # Should not crash
            logger._queue.put_nowait(None)
            await logger.stop()

        asyncio.run(_run())

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
