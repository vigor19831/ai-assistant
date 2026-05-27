"""Application configuration — Pydantic + env-prefix AI__."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "AppConfig",
    "ChatConfig",
    "ChunkerConfig",
    "CORSConfig",
    "EmbedderConfig",
    "LLMConfig",
    "load_config",
    "RAGConfig",
    "RerankerConfig",
    "SecurityConfig",
    "StorageConfig",
    "UIConfig",
    "VectorStoreConfig",
    "VisionConfig",
    "VoiceConfig",
]


class CORSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CORS_", extra="allow")
    allow_origins: list[str] = Field(default_factory=list)
    allow_credentials: bool = True
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class UIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_UI_", extra="allow")
    static_path: str = "./ui"


class ChatConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHAT_", extra="allow")
    history_limit: int = 10
    max_context_tokens: int | None = None
    tokenizer_model: str = "gpt-4o"
    tokenizer_local_dir: str = "./data/tokenizers"


class ChunkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHUNKER_", extra="allow")
    provider: str = "simple"
    chunk_size: int = 512
    chunk_overlap: int = 50


class EmbedderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_EMBEDDER_", extra="allow")
    provider: str = "mock"
    model: str = "text-embedding-3-small"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LLM_", extra="allow")
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 300.0
    stop_sequences: list[str] = Field(default_factory=list)
    # === Sampling ===
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=-1)
    min_p: float = Field(default=0.05, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)

class VectorStoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VECTOR_STORE_", extra="allow")
    provider: str = "memory"
    index_path: str = "./data/indices/default"
    metric: str = "l2"
    dim: int = 384


class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_STORAGE_", extra="allow")
    provider: str = "sqlite"
    db_path: str = "./data/storage.db"


class VoiceConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VOICE_", extra="allow")
    enabled: bool = False
    recognizer_provider: str = "whisper_local"
    synthesizer_provider: str = "piper"


class VisionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VISION_", extra="allow")
    enabled: bool = False
    provider: str = "clip_local"


class RerankerConfig(BaseSettings):
    """Reranker configuration — optional, backward compatible."""

    model_config = SettingsConfigDict(env_prefix="AI_RERANKER_", extra="allow")
    provider: str = "dummy"  # "dummy" | "api"
    model: str = "rerank-multilingual-v3.0"
    api_base: str = "https://api.cohere.com"
    api_key: str | None = None
    timeout: float = 30.0
    threshold: float = 0.3


class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_RAG_", extra="allow")
    steps: list[str] = Field(
        default_factory=lambda: [
            "embed_query",
            "retrieve",
            "rerank",
            "build_context",
            "generate",
        ]
    )
    prompt_version: str = "v1"
    prompt_name: str = "rag_strict"
    top_k: int = 5
    default_namespace: str = "default"
    relevance_threshold: float = 0.3


class SecurityConfig(BaseSettings):
    """Security configuration — loaded once at startup."""

    model_config = SettingsConfigDict(env_prefix="AI_SECURITY_", extra="allow")
    api_key: str | None = None
    rate_limit: str = "100/minute"
    max_body_size: int = 10_485_760
    allowed_hosts: list[str] = Field(default_factory=list)


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        extra="ignore",
    )
    app_name: str = "ai-assistant"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    config_version: str = "1.0.0"
    log_file: str | None = None
    cors: CORSConfig = Field(default_factory=CORSConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    @field_validator("rag", mode="before")
    @classmethod
    def _load_rag_steps(cls, v: Any) -> Any:
        if isinstance(v, dict) and "steps" in v and isinstance(v["steps"], str):
            return {**v, "steps": v["steps"].split(",")}
        return v


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML, fallback to env defaults.

    Args:
        path: Path to the YAML config file.

    Returns:
        Populated AppConfig instance.

    Raises:
        ValueError: If the file contains invalid YAML.
    """
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    try:
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {config_path}: {exc}") from exc
    return AppConfig(**data)
