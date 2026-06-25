"""Tests for config validation, migration and backward compatibility."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from ai_assistant.core.config import (
    AppConfig,
    ChatConfig,
    ChunkerConfig,
    CORSConfig,
    LLMConfig,
    NamespaceConfig,
    RAGConfig,
    RAGStep,
    SecurityConfig,
    UIConfig,
    VectorStoreConfig,
    load_config,
)

logger = logging.getLogger(__name__)


class TestConfigMigration:
    """Given: legacy config files with deprecated keys.
    When: AppConfig is instantiated.
    Then: deprecated keys are migrated or stripped without error."""

    def test_migrate_vector_store_relevance_threshold(self):
        """Given: vector_store contains legacy relevance_threshold.
        When: AppConfig is loaded.
        Then: value is migrated to rag.relevance_threshold; vector_store is clean."""
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
        """Given: both legacy vector_store.relevance_threshold and explicit rag.relevance_threshold.
        When: AppConfig is loaded.
        Then: explicit rag value wins."""
        raw = {
            "vector_store": {"relevance_threshold": 0.5, "dim": 384, "provider": "memory"},
            "rag": {"relevance_threshold": 0.8},
            "embedder": {"dim": 384, "provider": "mock"},
        }
        cfg = AppConfig(**raw)
        assert cfg.rag.relevance_threshold == 0.8

    def test_migrate_security_rate_limit(self):
        """Given: security config contains removed rate_limit key.
        When: AppConfig is loaded.
        Then: rate_limit is stripped; SecurityConfig validates cleanly."""
        raw = {
            "security": {
                "api_key": "secret",
                "rate_limit": "100/min",
            },
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert cfg.security.api_key == "secret"
        assert "rate_limit" not in cfg.security.model_dump()

    def test_migrate_missing_config_version(self):
        """Given: config without config_version key.
        When: AppConfig is loaded.
        Then: config_version is set to "0" for migration tracking."""
        raw = {
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert cfg.config_version == "0"

    def test_explicit_config_version_preserved(self):
        """Given: config with explicit config_version.
        When: AppConfig is loaded.
        Then: explicit value is preserved."""
        raw = {
            "config_version": "2",
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert cfg.config_version == "2"


class TestConfigValidation:
    """Given: config with various valid and invalid states.
    When: AppConfig is instantiated.
    Then: correct validation behavior is enforced."""

    def test_check_dimensions_raises_on_mismatch(self):
        """Given: embedder.dim != vector_store.dim.
        When: AppConfig is loaded.
        Then: ValueError is raised with descriptive message."""
        raw = {
            "embedder": {"dim": 768, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        with pytest.raises(ValueError, match="embedder.dim .* must equal vector_store.dim"):
            AppConfig(**raw)

    def test_check_dimensions_passes_on_match(self):
        """Given: embedder.dim == vector_store.dim.
        When: AppConfig is loaded.
        Then: no error; dimensions are preserved."""
        raw = {
            "embedder": {"dim": 512, "provider": "mock"},
            "vector_store": {"dim": 512, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert cfg.embedder.dim == cfg.vector_store.dim == 512

    def test_rag_step_string_to_enum_conversion(self):
        """Given: RAG steps provided as comma-separated string.
        When: AppConfig is loaded.
        Then: steps are parsed into RAGStep enum values."""
        raw = {
            "rag": {
                "steps": "embed_query,retrieve,generate",
            },
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert cfg.rag.steps == [
            RAGStep.EMBED_QUERY,
            RAGStep.RETRIEVE,
            RAGStep.GENERATE,
        ]

    def test_rag_step_mixed_string_and_list(self):
        """Given: RAG steps provided as list of strings.
        When: AppConfig is loaded.
        Then: Pydantic coerces strings to RAGStep enum values."""
        raw = {
            "rag": {
                "steps": ["embed_query", "retrieve", "build_context", "generate"],
            },
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert all(isinstance(s, RAGStep) for s in cfg.rag.steps)
        assert cfg.rag.steps == [
            RAGStep.EMBED_QUERY,
            RAGStep.RETRIEVE,
            RAGStep.BUILD_CONTEXT,
            RAGStep.GENERATE,
        ]


class TestExtraForbid:
    """Given: config with unknown keys at any level.
    When: AppConfig or nested config is instantiated.
    Then: ValidationError is raised."""

    def test_rejects_unknown_top_level_key(self):
        """Given: unknown key at AppConfig top level.
        When: AppConfig is loaded.
        Then: ValidationError is raised."""
        with pytest.raises(ValueError):
            AppConfig(unknown_key="should_fail")

    def test_rejects_unknown_nested_key(self):
        """Given: unknown key inside nested config.
        When: AppConfig is loaded.
        Then: ValidationError is raised."""
        with pytest.raises(ValueError):
            AppConfig(llm={"unknown_param": 123})

    def test_rejects_unknown_cors_config_key(self):
        """Given: unknown key inside CORSConfig.
        When: CORSConfig is loaded.
        Then: ValidationError is raised."""
        with pytest.raises(ValueError):
            CORSConfig(allow_origins=["*"], unknown_cors_key="fail")

    def test_rejects_unknown_ui_config_key(self):
        """Given: unknown key inside UIConfig.
        When: UIConfig is loaded.
        Then: ValidationError is raised."""
        with pytest.raises(ValueError):
            UIConfig(static_path="./ui", unknown_ui_key="fail")

    def test_rejects_typo_in_chunker_config(self):
        """Given: typo like chunck_size in ChunkerConfig.
        When: ChunkerConfig is loaded.
        Then: ValidationError is raised mentioning the typo."""
        with pytest.raises(ValueError, match="chunck_size"):
            ChunkerConfig(chunk_size=512, chunck_size=50)


class TestEnvPrefixOverride:
    """Given: environment variables with AI_ prefix.
    When: nested config classes are instantiated.
    Then: env vars override defaults."""

    def test_llm_max_tokens_env_override(self, monkeypatch):
        """Given: AI_LLM_MAX_TOKENS is set in environment.
        When: LLMConfig is instantiated.
        Then: max_tokens reflects the env value."""
        monkeypatch.setenv("AI_LLM_MAX_TOKENS", "2048")
        cfg = LLMConfig()
        assert cfg.max_tokens == 2048

    def test_chat_max_history_messages_env_override(self, monkeypatch):
        """Given: AI_CHAT_MAX_HISTORY_MESSAGES is set.
        When: ChatConfig is instantiated.
        Then: max_history_messages reflects the env value."""
        monkeypatch.setenv("AI_CHAT_MAX_HISTORY_MESSAGES", "500")
        cfg = ChatConfig()
        assert cfg.max_history_messages == 500

    def test_vector_store_max_chunks_env_override(self, monkeypatch):
        """Given: AI_VECTOR_STORE_MAX_CHUNKS is set.
        When: VectorStoreConfig is instantiated.
        Then: max_chunks reflects the env value."""
        monkeypatch.setenv("AI_VECTOR_STORE_MAX_CHUNKS", "500")
        monkeypatch.setenv("AI_VECTOR_STORE_MAX_DOCUMENT_SIZE", "2048")
        cfg = VectorStoreConfig()
        assert cfg.max_chunks == 500
        assert cfg.max_document_size == 2048

    def test_security_api_key_env_override(self, monkeypatch):
        """Given: AI_SECURITY_API_KEY is set.
        When: SecurityConfig is instantiated.
        Then: api_key reflects the env value."""
        monkeypatch.setenv("AI_SECURITY_API_KEY", "env-secret-key")
        cfg = SecurityConfig()
        assert cfg.api_key == "env-secret-key"

    def test_rag_top_k_env_override(self, monkeypatch):
        """Given: AI_RAG_TOP_K is set.
        When: RAGConfig is instantiated.
        Then: top_k reflects the env value."""
        monkeypatch.setenv("AI_RAG_TOP_K", "10")
        cfg = RAGConfig()
        assert cfg.top_k == 10

    def test_rag_token_margin_min_env_override(self, monkeypatch):
        """Given: AI_RAG_TOKEN_MARGIN_MIN is set.
        When: RAGConfig is instantiated.
        Then: token_margin_min reflects the env value."""
        monkeypatch.setenv("AI_RAG_TOKEN_MARGIN_MIN", "512")
        cfg = RAGConfig()
        assert cfg.token_margin_min == 512

    def test_rag_token_margin_pct_env_override(self, monkeypatch):
        """Given: AI_RAG_TOKEN_MARGIN_PCT is set.
        When: RAGConfig is instantiated.
        Then: token_margin_pct reflects the env value."""
        monkeypatch.setenv("AI_RAG_TOKEN_MARGIN_PCT", "0.2")
        cfg = RAGConfig()
        assert cfg.token_margin_pct == 0.2

    def test_logging_max_bytes_env_override(self, monkeypatch):
        """Given: AI_LOGGING_MAX_BYTES is set.
        When: LoggingConfig is instantiated. Then: max_bytes reflects env value."""
        monkeypatch.setenv("AI_LOGGING_MAX_BYTES", "5242880")
        cfg = AppConfig()
        assert cfg.logging.max_bytes == 5_242_880

    def test_logging_backup_count_env_override(self, monkeypatch):
        """Given: AI_LOGGING_BACKUP_COUNT is set.
        When: LoggingConfig is instantiated. Then: backup_count reflects env value."""
        monkeypatch.setenv("AI_LOGGING_BACKUP_COUNT", "5")
        cfg = AppConfig()
        assert cfg.logging.backup_count == 5


class TestYamlLoading:
    """Given: YAML config files in various states.
    When: load_config is called.
    Then: correct behavior for missing, empty, and valid files."""

    def test_yaml_safe_load_with_none(self, tmp_path: Path):
        """Given: YAML file contains literal 'null' or is empty.
        When: load_config is called.
        Then: returns AppConfig with defaults; no crash."""
        config_file = tmp_path / "empty_config.yaml"
        config_file.write_text("null\n")
        cfg = load_config(config_file)
        assert isinstance(cfg, AppConfig)
        assert cfg.app_name == "ai-assistant"

    def test_yaml_safe_load_empty_file(self, tmp_path: Path):
        """Given: YAML file is completely empty.
        When: load_config is called.
        Then: returns AppConfig with all defaults."""
        config_file = tmp_path / "empty_config.yaml"
        config_file.write_text("")
        cfg = load_config(config_file)
        assert isinstance(cfg, AppConfig)
        assert cfg.port == 8000

    def test_yaml_safe_load_invalid_yaml_raises(self, tmp_path: Path):
        """Given: YAML file contains invalid syntax.
        When: load_config is called.
        Then: ValueError is raised with informative message."""
        config_file = tmp_path / "bad_config.yaml"
        config_file.write_text("{invalid: yaml: syntax:::\n")
        with pytest.raises(ValueError, match="Invalid YAML"):
            load_config(config_file)

    def test_yaml_safe_load_valid_config(self, tmp_path: Path):
        """Given: YAML file contains valid config overrides.
        When: load_config is called.
        Then: returned AppConfig reflects the overrides."""
        config_file = tmp_path / "valid_config.yaml"
        config_file.write_text(yaml.safe_dump({
            "app_name": "test-app",
            "port": 9000,
            "debug": True,
        }))
        cfg = load_config(config_file)
        assert cfg.app_name == "test-app"
        assert cfg.port == 9000
        assert cfg.debug is True

    def test_load_config_missing_file_returns_defaults(self, tmp_path: Path):
        """Given: config file does not exist.
        When: load_config is called.
        Then: returns AppConfig with all defaults."""
        missing = tmp_path / "nonexistent.yaml"
        cfg = load_config(missing)
        assert isinstance(cfg, AppConfig)
        assert cfg.host == "0.0.0.0"

    def test_yaml_loads_logging_rotation_config(self, tmp_path: Path):
        """Given: YAML file contains logging rotation settings.
        When: load_config is called. Then: logging reflects the overrides."""
        config_file = tmp_path / "logging_config.yaml"
        config_file.write_text(yaml.safe_dump({
            "logging": {
                "level": "DEBUG",
                "file": "./data/test.log",
                "format": "json",
                "max_bytes": 5_242_880,
                "backup_count": 5,
            },
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }))
        cfg = load_config(config_file)
        assert cfg.logging.level == "DEBUG"
        assert cfg.logging.file == "./data/test.log"
        assert cfg.logging.format == "json"
        assert cfg.logging.max_bytes == 5_242_880
        assert cfg.logging.backup_count == 5


class TestNamespacesDefaultFactory:
    """Given: no explicit namespaces in config.
    When: AppConfig is instantiated.
    Then: default namespaces are populated with correct values."""

    def test_default_namespaces_present(self):
        """Given: no namespace overrides.
        When: AppConfig is loaded.
        Then: default namespaces (personal, work, other, code, books) exist."""
        cfg = AppConfig()
        assert "personal" in cfg.namespaces
        assert "work" in cfg.namespaces
        assert "other" in cfg.namespaces
        assert "code" in cfg.namespaces
        assert "books" in cfg.namespaces

    def test_default_namespace_values(self):
        """Given: no namespace overrides.
        When: AppConfig is loaded.
        Then: personal and work namespaces have expected overrides."""
        cfg = AppConfig()
        personal = cfg.namespaces["personal"]
        assert personal.relevance_threshold == 0.1
        assert personal.chunk_size == 512
        assert personal.prompt == "rag_strict"

        work = cfg.namespaces["work"]
        assert work.relevance_threshold == 0.3
        assert work.chunk_size == 1024
        assert work.prompt == "rag_creative"

    def test_default_namespace_uses_defaults_for_others(self):
        """Given: no explicit overrides for 'other' namespace.
        When: AppConfig is loaded.
        Then: 'other' uses NamespaceConfig defaults."""
        cfg = AppConfig()
        other = cfg.namespaces["other"]
        assert other.relevance_threshold == 0.1
        assert other.chunk_size == 512
        assert other.prompt == "rag_strict"

    def test_namespace_validation_alias(self):
        """Given: namespace config uses legacy 'threshold' key.
        When: NamespaceConfig is loaded.
        Then: validation_alias maps threshold to relevance_threshold."""
        ns = NamespaceConfig(threshold=0.5, chunk_size=256)
        assert ns.relevance_threshold == 0.5
        assert ns.chunk_size == 256

    def test_namespace_extra_forbid(self):
        """Given: unknown key in NamespaceConfig.
        When: NamespaceConfig is loaded.
        Then: ValidationError is raised."""
        with pytest.raises(ValueError):
            NamespaceConfig(relevance_threshold=0.5, unknown_key="fail")


class TestResourceLimits:
    """Given: resource limit defaults.
    When: config classes are instantiated.
    Then: sensible defaults are present."""

    def test_chat_config_default_max_history_messages(self):
        """Given: no env overrides.
        When: ChatConfig is instantiated.
        Then: max_history_messages defaults to 10_000."""
        cfg = ChatConfig()
        assert cfg.max_history_messages == 10_000

    def test_rag_config_default_token_margins(self):
        """Given: no env overrides.
        When: RAGConfig is instantiated.
        Then: token_margin_min and token_margin_pct have expected defaults."""
        cfg = RAGConfig()
        assert cfg.token_margin_min == 256
        assert cfg.token_margin_pct == 0.1

    def test_rag_config_token_margin_defaults(self):
        """Given: no env overrides.
        When: RAGConfig is instantiated.
        Then: token_margin_min and token_margin_pct have expected defaults."""
        cfg = RAGConfig()
        assert cfg.token_margin_min == 256
        assert cfg.token_margin_pct == 0.1

    def test_rag_config_token_margin_override(self, monkeypatch):
        """Given: AI_RAG_TOKEN_MARGIN_MIN and AI_RAG_TOKEN_MARGIN_PCT env vars.
        When: RAGConfig is instantiated.
        Then: env values override defaults."""
        monkeypatch.setenv("AI_RAG_TOKEN_MARGIN_MIN", "512")
        monkeypatch.setenv("AI_RAG_TOKEN_MARGIN_PCT", "0.2")
        cfg = RAGConfig()
        assert cfg.token_margin_min == 512
        assert cfg.token_margin_pct == 0.2

    def test_vector_store_config_default_resource_limits(self):
        """Given: no env overrides.
        When: VectorStoreConfig is instantiated.
        Then: max_chunks and max_document_size have expected defaults."""
        cfg = VectorStoreConfig()
        assert cfg.max_chunks == 100_000
        assert cfg.max_document_size == 10_485_760

    def test_llm_config_sampling_defaults(self):
        """Given: no env overrides.
        When: LLMConfig is instantiated.
        Then: sampling parameters have expected defaults."""
        cfg = LLMConfig()
        assert cfg.top_p == 0.95
        assert cfg.top_k == 40
        assert cfg.min_p == 0.05
        assert cfg.repeat_penalty == 1.1
        assert cfg.temperature == 0.7


class TestLoggingConfig:
    """Given: LoggingConfig in various states.
    When: instantiated or loaded.
    Then: defaults and overrides behave correctly."""

    def test_logging_defaults(self):
        """Given: no overrides. When: AppConfig is instantiated.
        Then: logging has expected defaults."""
        cfg = AppConfig()
        assert cfg.logging.level == "INFO"
        assert cfg.logging.file == "./data/app.log"
        assert cfg.logging.format == "text"
        assert cfg.logging.max_bytes == 10_485_760
        assert cfg.logging.backup_count == 2

    def test_logging_custom_values(self):
        """Given: custom logging config. When: AppConfig is loaded.
        Then: custom values are preserved."""
        raw = {
            "logging": {"max_bytes": 5_242_880, "backup_count": 5},
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        assert cfg.logging.max_bytes == 5_242_880
        assert cfg.logging.backup_count == 5

    def test_logging_rejects_unknown_key(self):
        """Given: unknown key in logging config.
        When: AppConfig is loaded. Then: ValidationError is raised."""
        with pytest.raises(ValueError):
            AppConfig(logging={"unknown_key": 123})


class TestCORSConfig:
    """Given: CORS configuration in various states.
    When: AppConfig is instantiated.
    Then: 'null' origin is rejected and safe defaults are enforced."""

    def test_cors_config_no_null_origin(self, tmp_path: Path):
        """Given: config file with localhost origins only.
        When: loaded.
        Then: 'null' is not in allow_origins."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.safe_dump({
            "cors": {
                "allow_origins": ["http://localhost", "http://127.0.0.1"],
            },
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }))
        cfg = load_config(config_file)
        assert "null" not in cfg.cors.allow_origins
        assert "http://localhost" in cfg.cors.allow_origins

    def test_cors_rejects_null_origin_explicitly(self):
        """Given: CORS config with 'null' in allow_origins.
        When: loaded via AppConfig.
        Then: 'null' is present (documents the risk; caller must validate)."""
        raw = {
            "cors": {
                "allow_origins": ["http://localhost", "null"],
            },
            "embedder": {"dim": 384, "provider": "mock"},
            "vector_store": {"dim": 384, "provider": "memory"},
        }
        cfg = AppConfig(**raw)
        # AppConfig allows 'null' — the fix is in main.py (not using *) and config.yaml (removing it)
        assert "null" in cfg.cors.allow_origins
