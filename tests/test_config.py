"""Tests for config validation, migration and backward compatibility."""

from __future__ import annotations

import pytest

from ai_assistant.core.config import AppConfig


class TestConfigMigration:
    def test_migrate_vector_store_relevance_threshold(self):
        """Legacy vector_store.relevance_threshold is migrated to rag."""
        raw = {
            "vector_store": {
                "relevance_threshold": 0.5,
                "dim": 384,
                "provider": "memory",
            },
            "embedder": {"dim": 384, "provider": "mock"},
        }
        cfg = AppConfig(**raw)
        assert cfg.rag.relevance_threshold == 0.5
        # vector_store must NOT contain the legacy key (extra="forbid")
        assert "relevance_threshold" not in cfg.vector_store.model_dump()

    def test_migrate_does_not_override_explicit_rag_threshold(self):
        """Explicit rag.relevance_threshold wins over legacy migration."""
        raw = {
            "vector_store": {"relevance_threshold": 0.5, "dim": 384, "provider": "memory"},
            "rag": {"relevance_threshold": 0.8},
            "embedder": {"dim": 384, "provider": "mock"},
        }
        cfg = AppConfig(**raw)
        assert cfg.rag.relevance_threshold == 0.8

    def test_check_dimensions_raises_on_mismatch(self):
        """embedder.dim != vector_store.dim raises ValueError immediately."""
        raw = {
            "embedder": {"dim": 768, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        with pytest.raises(ValueError, match="embedder.dim .* must equal vector_store.dim"):
            AppConfig(**raw)

    def test_check_dimensions_passes_on_match(self):
        """Matching dimensions validate silently."""
        raw = {
            "embedder": {"dim": 512, "provider": "mock"},
            "vector_store": {"dim": 512, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert cfg.embedder.dim == cfg.vector_store.dim == 512


class TestExtraForbid:
    def test_rejects_unknown_top_level_key(self):
        with pytest.raises(ValueError):
            AppConfig(unknown_key="should_fail")

    def test_rejects_unknown_nested_key(self):
        with pytest.raises(ValueError):
            AppConfig(llm={"unknown_param": 123})
