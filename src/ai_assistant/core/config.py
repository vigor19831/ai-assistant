"""Application configuration — Pydantic + env-prefix AI__."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai_assistant.core.constants import CHAT_NS_PREFIX


def _get_chat_namespace(base_namespace: str) -> str:
    """Derive isolated chat namespace from base namespace.

    Guarantees no collision with user-created namespaces by reserving
    the CHAT_NS_PREFIX prefix. Raises ValueError if base_namespace
    already starts with the reserved prefix (indicates misuse).
    """
    if base_namespace.startswith(CHAT_NS_PREFIX):
        raise ValueError(
            "Namespace '" + base_namespace + "' uses reserved prefix '" + CHAT_NS_PREFIX + "'"
        )
    return CHAT_NS_PREFIX + base_namespace


__all__ = [
    "AppConfig",
    "ChatConfig",
    "TokenizerConfig",
    "ChunkerConfig",
    "CORSConfig",
    "EmbedderConfig",
    "LLMConfig",
    "load_config",
    "CHAT_NS_PREFIX",
    "_get_chat_namespace",
    "NamespaceConfig",
    "RAGConfig",
    "RerankerConfig",
    "SecurityConfig",
    "SourceConfig",
    "StorageConfig",
    "UIConfig",
    "VectorStoreConfig",
]


class CORSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CORS_", extra="forbid")
    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = False
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class UIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_UI_", extra="forbid")
    static_path: str = "./ui"


class ChatConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHAT_", extra="forbid")
    history_limit: int = 10
    max_history_messages: int = 10_000
    max_context_tokens: int | None = None


class TokenizerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_TOKENIZER_", extra="forbid")
    provider: str = "tiktoken"
    local_dir: str = "./data/tokenizers"


class ChunkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHUNKER_", extra="forbid")
    provider: str = "simple"
    chunk_size: int = 512
    chunk_overlap: int = 50


class EmbedderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_EMBEDDER_", extra="forbid")
    provider: str = "mock"
    model: str = "text-embedding-3-small"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0
    connect_timeout: float | None = None
    n_gpu_layers: int = 0
    n_batch: int = 512
    n_ubatch: int = 64
    mmap: bool = True
    mlock: bool = False


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LLM_", extra="forbid")
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    available_models: list[str] = Field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 300.0
    connect_timeout: float | None = None
    stop_sequences: list[str] = Field(default_factory=list)
    system_message: str | None = None
    # === Sampling ===
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=-1)
    min_p: float = Field(default=0.05, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    server_context_size: int | None = None
    # === llama.cpp / local backend runtime ===
    n_gpu_layers: int = 99
    n_batch: int = 512
    n_ubatch: int = 64
    mmap: bool = True
    mlock: bool = False


class VectorStoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VECTOR_STORE_", extra="forbid")
    provider: str = "memory"
    index_path: str = "./data/indices/default"
    metric: str = "l2"
    dim: int = 384
    max_chunks: int = 100_000
    max_document_size: int = 10_485_760


class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_STORAGE_", extra="forbid")
    provider: str = "sqlite"
    db_path: str = "./data/storage.db"


class RerankerConfig(BaseSettings):
    """Reranker configuration — optional, backward compatible."""

    model_config = SettingsConfigDict(env_prefix="AI_RERANKER_", extra="forbid")
    provider: str | None = None  # "api" or None for no reranker
    model: str = "rerank-multilingual-v3.0"
    api_base: str = "https://api.cohere.com"
    api_key: str | None = None
    timeout: float = 30.0
    threshold: float = 0.3


class RAGStep(StrEnum):
    """RAG pipeline step identifiers — type-safe replacement for raw strings."""

    CONDENSE_QUESTION = "condense_question"
    EMBED_QUERY = "embed_query"
    HYDE_QUERY = "hyde_query"
    RETRIEVE = "retrieve"
    RERANK = "rerank"
    BUILD_CONTEXT = "build_context"
    GENERATE = "generate"


class SourceConfig(BaseModel):
    """Document source configuration — read-only path with filtering."""

    model_config = ConfigDict(extra="forbid")
    namespace: str
    path: str
    include: list[str] = Field(default_factory=lambda: ["*.md", "*.txt"])
    recursive: bool = True

    @field_validator("path")
    @classmethod
    def _reject_traversal(cls, v: str) -> str:
        """Reject path traversal in source paths."""
        v = v.strip()
        if not v:
            raise ValueError("path must be non-empty")
        if ".." in Path(v).parts:
            raise ValueError(f"path contains traversal, got: {v}")
        return v


class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_RAG_", extra="forbid")
    steps: list[RAGStep] = Field(
        default_factory=lambda: [
            RAGStep.EMBED_QUERY,
            RAGStep.RETRIEVE,
            RAGStep.RERANK,
            RAGStep.BUILD_CONTEXT,
            RAGStep.GENERATE,
        ]
    )
    prompt_version: str = "v1"
    prompt_name: str = "rag_strict"
    top_k: int = 5
    default_namespace: str = "default"
    threshold: float = 0.1
    max_tool_iterations: int = 5
    token_margin_min: int = 256
    token_margin_pct: float = 0.1
    sources: list[SourceConfig] = Field(default_factory=list)
    chat_exports_root: str = "data/chat_exports"
    index_chat_exports: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_documents_root_to_sources(cls, v: Any) -> Any:
        """Backward-compatible loader: migrate documents_root → sources list.

        If 'sources' is absent but 'documents_root' is present,
        create a single SourceConfig from documents_root with default filters.
        If both are present, append documents_root as an additional source
        to prevent silent data loss.
        Always strips documents_root to satisfy extra="forbid".
        """
        if type(v) is not dict:
            return v
        if "documents_root" in v:
            migrated_source = {
                "namespace": "default",
                "path": v["documents_root"],
                "include": ["*.md", "*.txt", "*.py", "*.json", "*.yaml", "*.yml", "*.csv", "*.log"],
                "recursive": True,
            }
            existing_sources = v.get("sources")
            if type(existing_sources) is list:
                # Prepend migrated source so old path is not lost
                v = {
                    **v,
                    "sources": [migrated_source, *existing_sources],
                }
            else:
                # Migrate old flat folder to new source format
                v = {
                    **v,
                    "sources": [migrated_source],
                }
            # Always remove the old key so extra="forbid" doesn't choke
            v = {k: val for k, val in v.items() if k != "documents_root"}
        return v

    @field_validator("chat_exports_root")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        """Normalize path: strip trailing slashes, reject absolute paths and traversal."""
        v = v.strip()
        if not v:
            raise ValueError("path must be non-empty")
        if v.startswith("/") or v.startswith("\\") or v.startswith("~"):
            raise ValueError(f"path must be relative, got: {v}")
        # Reject path traversal attempts before they reach filesystem
        normalized = Path(v).as_posix()
        if ".." in normalized.split("/"):
            raise ValueError(f"path contains traversal, got: {v}")
        return v.rstrip("/").rstrip("\\")


class SecurityConfig(BaseSettings):
    """Security configuration — loaded once at startup."""

    model_config = SettingsConfigDict(env_prefix="AI_SECURITY_", extra="forbid")
    api_key: str | None = None
    admin_enabled: bool = False
    max_body_size: int = 10_485_760
    allowed_hosts: list[str] = Field(default_factory=list)
    openai_routes_require_auth: bool = False


class NamespaceConfig(BaseModel):
    """Per-namespace RAG overrides."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    threshold: float = Field(default=0.1)
    chunk_size: int = 512
    prompt: str = "rag_strict"
    prefix: str | None = Field(
        default=None,
        min_length=1,
        description="Single-character prefix for RAG query routing. Empty string is not allowed.",
    )


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LOGGING_", extra="forbid")
    level: str = "INFO"
    file: str | None = "./data/app.log"
    format: str = "text"  # "text" or "json"
    max_bytes: int = 10_485_760  # 10 MB
    backup_count: int = 2


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        extra="forbid",
    )
    app_name: str = "ai-assistant"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    config_version: str = "1"
    log_file: str | None = None
    cors: CORSConfig = Field(default_factory=CORSConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    tokenizer: TokenizerConfig = Field(default_factory=TokenizerConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    namespaces: dict[str, NamespaceConfig] = Field(default_factory=dict)
    @model_validator(mode="before")
    @classmethod
    def _migrate_config_version(cls, v: Any) -> Any:
        """Backward-compatible loader: set config_version to "0" if absent.

        Allows future model_validators to branch on config_version when
        applying breaking migrations.
        """
        if type(v) is not dict:
            return v
        if "config_version" not in v:
            v = {**v, "config_version": "0"}
        return v

    @field_validator("rag", mode="before")
    @classmethod
    def _load_rag_steps(cls, v: Any) -> Any:
        if type(v) is dict and "steps" in v and type(v["steps"]) is str:  # noqa: UP037
            return {**v, "steps": [s.strip() for s in v["steps"].split(",")]}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_vector_store_relevance_threshold(cls, v: Any) -> Any:
        """Backward-compatible loader: migrate vector_store.relevance_threshold → rag.threshold."""
        if type(v) is not dict:
            return v
        vs = v.get("vector_store")
        if type(vs) is dict and "relevance_threshold" in vs:
            rag = v.get("rag", {})
            if type(rag) is dict and "threshold" not in rag:
                rag = {**rag, "threshold": vs["relevance_threshold"]}
                v = {**v, "rag": rag}
            # Strip the removed field so VectorStoreConfig(extra="forbid") doesn't choke
            vs = {k: val for k, val in vs.items() if k != "relevance_threshold"}
            v = {**v, "vector_store": vs}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_security_rate_limit(cls, v: Any) -> Any:
        """Backward-compatible loader: strip removed security.rate_limit field."""
        if type(v) is not dict:
            return v
        sec = v.get("security")
        if type(sec) is dict and "rate_limit" in sec:
            # rate_limit was removed — strip it so SecurityConfig(extra="forbid") doesn't choke
            sec = {k: val for k, val in sec.items() if k != "rate_limit"}
            v = {**v, "security": sec}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_relevance_threshold_to_threshold(cls, v: Any) -> Any:
        """Backward-compatible loader: migrate relevance_threshold → threshold.

        Applies to both rag.* and namespaces.*.relevance_threshold.
        New key takes precedence if both are present.
        """
        if type(v) is not dict:
            return v

        # Migrate RAGConfig
        rag = v.get("rag")
        if type(rag) is dict and "relevance_threshold" in rag and "threshold" not in rag:
            rag = {**rag, "threshold": rag["relevance_threshold"]}
            rag = {k: val for k, val in rag.items() if k != "relevance_threshold"}
            v = {**v, "rag": rag}

        # Migrate NamespaceConfig entries
        namespaces = v.get("namespaces")
        if type(namespaces) is dict:
            migrated_ns: dict[str, Any] = {}
            for ns_name, ns_cfg in namespaces.items():
                if type(ns_cfg) is dict and "relevance_threshold" in ns_cfg and "threshold" not in ns_cfg:
                    ns_cfg = {**ns_cfg, "threshold": ns_cfg["relevance_threshold"]}
                    ns_cfg = {k: val for k, val in ns_cfg.items() if k != "relevance_threshold"}
                migrated_ns[ns_name] = ns_cfg
            v = {**v, "namespaces": migrated_ns}

        return v

    @model_validator(mode="after")
    def _check_dimensions(self) -> AppConfig:
        if self.embedder.dim != self.vector_store.dim:
            raise ValueError(
                f"embedder.dim ({self.embedder.dim}) must equal "
                f"vector_store.dim ({self.vector_store.dim})"
            )
        return self


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML.

    Args:
        path: Path to the YAML config file. Defaults to config.yaml.

    Returns:
        Populated AppConfig instance. pydantic-settings env vars
        take highest precedence.

    Raises:
        FileNotFoundError: If config file does not exist.
        ValueError: If file contains invalid YAML.
        ValidationError: If config contains unknown keys.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            f"Copy config.example.yaml to config.yaml and edit for your setup."
        )

    try:
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {config_path}: {exc}") from exc

    return AppConfig(**data)
