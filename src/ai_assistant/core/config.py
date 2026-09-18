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


def get_chat_namespace(base_namespace: str) -> str:
    """Derive isolated chat namespace from base namespace.

    Guarantees no collision with user-created namespaces by reserving
    the CHAT_NS_PREFIX prefix. Raises ValueError if base_namespace
    already starts with the reserved prefix (indicates misuse).
    """
    if base_namespace.startswith(CHAT_NS_PREFIX):
        raise ValueError(
            "Namespace '"
            + base_namespace
            + "' uses reserved prefix '"
            + CHAT_NS_PREFIX
            + "'"
        )
    return CHAT_NS_PREFIX + base_namespace


# CHAT_NS_PREFIX re-exported from constants for API consumers
# (mypy: anything outside __all__ is not an explicit export).
__all__ = [
    "CHAT_NS_PREFIX",
    "AppConfig",
    "ArchivistConfig",
    "CORSConfig",
    "ChatConfig",
    "ChunkerConfig",
    "EmbedderConfig",
    "LLMConfig",
    "LexicalIndexConfig",
    "LoggingConfig",
    "NamespaceConfig",
    "RAGConfig",
    "RAGStep",
    "RerankerConfig",
    "SecurityConfig",
    "SourceConfig",
    "StorageConfig",
    "TokenizerConfig",
    "UIConfig",
    "VectorStoreConfig",
    "get_chat_namespace",
    "load_config",
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
    max_context_tokens: int | None = None
    # Per-process limit. Total = this * uvicorn workers. Tune for VRAM/RAM.
    max_concurrent_chat: int = Field(default=5, ge=1)

class TokenizerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_TOKENIZER_", extra="forbid")
    provider: str = "tiktoken"
    local_dir: str = "./data/tokenizers"
    model_name: str = "cl100k_base"


class ChunkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHUNKER_", extra="forbid")
    provider: str = "simple"
    chunk_size: int = 512
    chunk_overlap: int = 50


class EmbedderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_EMBEDDER_", extra="forbid")
    provider: str = "mock"
    # Drift #154 (offline-first): no silent cloud-model default — a
    # configured remote provider must name its model (enforced at
    # startup by _check_explicit_models).
    model: str = ""
    # Drift #154: no silent cloud-endpoint default either — with an
    # OPENAI_API_KEY in the env a forgotten api_base spent real money.
    api_base: str = ""
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0
    connect_timeout: float | None = None
    n_gpu_layers: int = 0


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LLM_", extra="forbid")
    provider: str = "mock"
    # Drift #154 (offline-first): no silent cloud-model default.
    model: str = ""
    # Drift #154: no silent cloud-endpoint default.
    api_base: str = ""
    api_key: str | None = None
    available_models: list[str] = Field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout: float = 300.0
    connect_timeout: float | None = None
    stop_sequences: list[str] = Field(default_factory=list)
    system_message: str | None = None
    # === Sampling ===
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    server_context_size: int | None = None
    # === llama.cpp / local backend runtime (read by run_servers.py) ===
    n_gpu_layers: int = 99


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


class LexicalIndexConfig(BaseSettings):
    """Lexical (exact-term) index configuration — optional.

    Absent section = hybrid retrieval off, dense-only behavior
    (hybrid stage 3). provider selects the adapter ("bm25");
    index_path is the directory of the lexical index files, kept
    separate from the vector index_path so neither store lists the
    other's files.
    """

    model_config = SettingsConfigDict(env_prefix="AI_LEXICAL_INDEX_", extra="forbid")
    provider: str = "bm25"
    index_path: str = "./data/lexical_indices"


class RerankerConfig(BaseSettings):
    """Reranker configuration — optional, backward compatible."""

    model_config = SettingsConfigDict(env_prefix="AI_RERANKER_", extra="forbid")
    provider: str | None = None  # "api" or None for no reranker
    # Drift #154 (offline-first): no silent cloud-model default.
    model: str = ""
    # Drift #154: no silent cloud-endpoint default.
    api_base: str = ""
    api_key: str | None = None
    timeout: float = 30.0
    # Read by run_servers.py (never duplicated in run_servers.yaml
    # extra_args — drift #60). 0 = CPU.
    n_gpu_layers: int = 0


class ArchivistConfig(BaseSettings):
    """Atom-extraction LLM profile (scripts/prepare_docs.py --atoms).

    Read directly from config.yaml by the CLI script; the app itself
    does not use it. All knobs a model change touches: changing the
    LLM edits this section, never the script (single source of truth).
    """

    model_config = SettingsConfigDict(env_prefix="AI_ARCHIVIST_", extra="forbid")
    llm_api_base: str = "http://127.0.0.1:8080/v1/chat/completions"
    # None/empty = omit the model field: a single-model local server
    # routes the request without it (verified 2026-09-02).
    llm_model: str | None = None
    temperature: float = 0.0
    timeout: float = 300.0
    # Part budget in bytes, derived from the LLM context window:
    # ctx(8192) - instruction(~800) - answer(~1500) = ~5800 tokens
    # * ~3.5 bytes/token RU/EN -> 12000.
    part_bytes: int = 12_000


class RAGStep(StrEnum):
    """RAG pipeline step identifiers — type-safe replacement for raw strings."""

    CONDENSE_QUESTION = "condense_question"
    EMBED_QUERY = "embed_query"
    HYDE_QUERY = "hyde_query"
    MULTI_QUERY_RETRIEVE = "multi_query_retrieve"
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
    token_margin_min: int = 256
    token_margin_pct: float = 0.1
    sources: list[SourceConfig] = Field(default_factory=list)
    chat_exports_root: str = "data/chat_exports"
    index_chat_exports: bool = False
    # Date campaign stage 2 (variant 4b): month-name dictionary for
    # date-phrase parsing ("what did I decide in March"). Lives in
    # config — data, not code: src stays language-agnostic. Absent
    # section = digital date forms only ("2026-03", "03.2026");
    # pure optional addition, no config_version bump (drift #138).
    date_month_names: dict[str, int] = Field(default_factory=dict)
    # Prepositions are language data too ("in March", "za mart"):
    # which words may precede a month name in a query. Absent = no
    # phrase parsing (digital forms still work).
    date_prepositions: list[str] = Field(default_factory=list)

    @field_validator("date_month_names")
    @classmethod
    def _validate_month_numbers(cls, v: dict[str, int]) -> dict[str, int]:
        for name, month in v.items():
            if not 1 <= month <= 12:
                raise ValueError(
                    f"date_month_names: month for {name!r} must be "
                    f"1-12, got {month}"
                )
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_documents_root_to_sources(cls, v: Any) -> Any:
        """Backward-compatible loader: migrate documents_root to a sources list.

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
                "include": [
                    "*.md",
                    "*.txt",
                    "*.py",
                    "*.json",
                    "*.yaml",
                    "*.yml",
                    "*.csv",
                    "*.log",
                ],
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
        """Normalize path: strip trailing slashes, reject absolute paths
        and traversal."""
        v = v.strip()
        if not v:
            raise ValueError("path must be non-empty")
        if (
            v.startswith("/")
            or v.startswith("\\")
            or v.startswith("~")
            or (len(v) >= 2 and v[1] == ":")
        ):
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
    openai_routes_require_auth: bool = True

class NamespaceConfig(BaseModel):
    """Per-namespace RAG overrides."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    chunk_size: int = 512
    prompt: str = "rag_strict"
    prefix: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Short prefix for RAG query routing (e.g. '000'). "
            "Empty string is not allowed."
        ),
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
    config_version: str = "4"
    cors: CORSConfig = Field(default_factory=CORSConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    tokenizer: TokenizerConfig = Field(default_factory=TokenizerConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    lexical_index: LexicalIndexConfig | None = Field(default=None)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    archivist: ArchivistConfig = Field(default_factory=ArchivistConfig)
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
        # drift #121: max_history_messages removed — dead field, no
        # reader anywhere (audit M2, grep over src/scripts/tests/run_*).
        # Absorb old configs silently instead of failing them.
        if "max_history_messages" in v:
            del v["max_history_messages"]
        return v

    @field_validator("rag", mode="before")
    @classmethod
    def _load_rag_steps(cls, v: Any) -> Any:
        if type(v) is dict and "steps" in v and type(v["steps"]) is str:
            return {**v, "steps": [s.strip() for s in v["steps"].split(",")]}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_security_rate_limit(cls, v: Any) -> Any:
        """Backward-compatible loader: strip removed security.rate_limit field."""
        if type(v) is not dict:
            return v
        sec = v.get("security")
        if type(sec) is dict and "rate_limit" in sec:
            # rate_limit was removed — strip it so SecurityConfig(extra="forbid")
            # doesn't choke
            sec = {k: val for k, val in sec.items() if k != "rate_limit"}
            v = {**v, "security": sec}
        return v

    @model_validator(mode="before")
    @classmethod
    def _strip_deprecated_fields(cls, v: Any) -> Any:
        """Backward-compatible loader: remove orphaned v2 fields.

        log_file was replaced by logging.file.
        max_tool_iterations was never wired to any feature.
        """
        if type(v) is not dict:
            return v
        v = {k: val for k, val in v.items() if k != "log_file"}
        rag = v.get("rag")
        if type(rag) is dict:
            rag = {k: val for k, val in rag.items() if k != "max_tool_iterations"}
            v = {**v, "rag": rag}
        return v

    @model_validator(mode="after")
    def _check_dimensions(self) -> AppConfig:
        if self.embedder.dim != self.vector_store.dim:
            raise ValueError(
                f"embedder.dim ({self.embedder.dim}) must equal "
                f"vector_store.dim ({self.vector_store.dim})"
            )
        return self

    @model_validator(mode="after")
    def _check_explicit_models(self) -> AppConfig:
        """Offline-first guard (drift #154): a configured remote
        provider must name its model — an empty default fails loudly
        at startup instead of silently requesting a cloud model.
        Mock providers ignore the model field and are exempt; the
        archivist's llm_model=null pattern is a different contract
        (drift #132) and untouched.
        """
        if self.embedder.provider == "openai_compatible" and not self.embedder.model:
            raise ValueError(
                "embedder.model is required when provider is "
                "'openai_compatible': set your embedding model name"
            )
        if self.embedder.provider == "openai_compatible" and not self.embedder.api_base:
            raise ValueError(
                "embedder.api_base is required when provider is "
                "'openai_compatible': set your embedding server URL"
            )
        if self.llm.provider == "openai_compatible" and not self.llm.model:
            raise ValueError(
                "llm.model is required when provider is "
                "'openai_compatible': set your model name"
            )
        if self.llm.provider == "openai_compatible" and not self.llm.api_base:
            raise ValueError(
                "llm.api_base is required when provider is "
                "'openai_compatible': set your LLM server URL"
            )
        if self.reranker.provider in ("api", "local") and not self.reranker.model:
            raise ValueError(
                "reranker.model is required when provider is "
                "'api' or 'local': set your reranker model name"
            )
        if self.reranker.provider in ("api", "local") and not self.reranker.api_base:
            raise ValueError(
                "reranker.api_base is required when provider is "
                "'api' or 'local': set your reranker server URL"
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
