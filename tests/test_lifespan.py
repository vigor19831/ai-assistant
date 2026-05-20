"""Tests for api/lifespan.py — startup/shutdown lifecycle.

Validates graceful shutdown, index persistence, and error resilience.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.deps import AppState, init_adapters
from api.lifespan import _load_config, lifespan
from core.config import AppConfig

# ── _load_config ──


class TestLoadConfig:
    def test_reads_from_env_var(self, monkeypatch, tmp_path):
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text("app_name: env-test\nport: 7777")
        monkeypatch.setenv("AI_CONFIG_PATH", str(cfg_file))
        cfg = _load_config()
        assert cfg.app_name == "env-test"
        assert cfg.port == 7777

    def test_fallback_to_default(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text("app_name: default-test\nport: 8888")
        # Clear env var
        monkeypatch.delenv("AI_CONFIG_PATH", raising=False)
        cfg = _load_config()
        assert cfg.app_name == "default-test"


# ── lifespan context manager ──


class TestLifespan:
    @pytest.mark.asyncio
    async def test_yields_after_init(self):
        """lifespan should init adapters, yield, then shutdown."""
        app = MagicMock()

        with patch("api.lifespan._load_config", return_value=AppConfig()):
            with patch("api.lifespan.init_adapters", new_callable=AsyncMock):
                with patch("api.lifespan.get_metrics_logger") as mock_metrics:
                    mock_metrics.return_value.start = MagicMock()
                    mock_metrics.return_value.stop = AsyncMock()

                    async with lifespan(app) as _:
                        mock_metrics.return_value.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_saves_indices(self):
        """On shutdown, indices should be saved to disk."""
        app = MagicMock()
        mock_state = MagicMock()
        mock_state.llm = None
        mock_state.embedder = None
        mock_state.vector_store = MagicMock()
        mock_state.vector_store.list_namespaces = AsyncMock(
            return_value=["default", "personal"]
        )
        mock_state.vector_store.save = AsyncMock(return_value=None)

        with patch(
            "api.lifespan._load_config",
            return_value=AppConfig(
                vector_store={
                    "provider": "memory",
                    "dim": 384,
                    "metric": "l2",
                    "index_path": "./data/indices/test",
                }
            ),
        ):
            with patch("api.lifespan.init_adapters", new_callable=AsyncMock):
                with patch("api.lifespan.get_metrics_logger") as mock_metrics:
                    mock_metrics.return_value.start = MagicMock()
                    mock_metrics.return_value.stop = AsyncMock()

                    async with lifespan(app) as _:
                        app.state.app_state = mock_state
                        pass  # Exit context to trigger shutdown

                    # Verify save was called for each namespace
                    assert mock_state.vector_store.save.await_count == 2
                    mock_state.vector_store.save.assert_any_await(
                        "./data/indices/test", namespace="default"
                    )
                    mock_state.vector_store.save.assert_any_await(
                        "./data/indices/test", namespace="personal"
                    )

    @pytest.mark.asyncio
    async def test_shutdown_handles_missing_state(self):
        """If get_state raises RuntimeError, shutdown should not crash."""
        app = MagicMock()

        with patch("api.lifespan._load_config", return_value=AppConfig()):
            with patch("api.lifespan.init_adapters", new_callable=AsyncMock):
                with patch("api.lifespan.get_metrics_logger") as mock_metrics:
                    mock_metrics.return_value.start = MagicMock()
                    mock_metrics.return_value.stop = AsyncMock()

                    async with lifespan(app) as _:
                        pass  # Should not raise on shutdown

    @pytest.mark.asyncio
    async def test_lifespan_creates_app_state(self):
        """lifespan must create app.state.app_state with initialized fields."""
        from fastapi import FastAPI

        app = FastAPI(lifespan=lifespan)

        with patch("api.lifespan._load_config", return_value=AppConfig()):
            with patch("api.lifespan.get_metrics_logger") as mock_metrics:
                mock_metrics.return_value.start = MagicMock()
                mock_metrics.return_value.stop = AsyncMock()

                async with lifespan(app):
                    assert hasattr(app.state, "app_state")
                    assert isinstance(app.state.app_state, AppState)
                    assert app.state.app_state.chunker is not None
                    assert app.state.app_state.embedder is not None
                    assert app.state.app_state.llm is not None
                    assert app.state.app_state.vector_store is not None
                    assert app.state.app_state.pipeline is not None


# ── init_adapters ──


class TestInitAdaptersDirect:
    @pytest.mark.asyncio
    async def test_populates_state_fields(self):
        """init_adapters should mutate state with real adapters."""
        from core.config import AppConfig

        cfg = AppConfig()
        cfg.chunker.provider = "simple"
        cfg.embedder.provider = "mock"
        cfg.llm.provider = "mock"
        cfg.vector_store.provider = "memory"
        cfg.reranker.provider = "dummy"
        cfg.storage.provider = "sqlite"
        cfg.voice.enabled = False
        cfg.vision.enabled = False

        state = AppState(config=cfg)
        await init_adapters(state)

        assert state.chunker is not None
        assert state.embedder is not None
        assert state.llm is not None
        assert state.vector_store is not None
        assert state.pipeline is not None
