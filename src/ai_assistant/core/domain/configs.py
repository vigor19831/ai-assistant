"""core/domain/configs.py"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkerConfigData:
    chunk_size: int = 512
    chunk_overlap: int = 50


@dataclass(frozen=True, slots=True)
class EmbedderConfigData:
    model: str = "text-embedding-3-small"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0


@dataclass(frozen=True, slots=True)
class LLMConfigData:
    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 300.0
    server_context_size: int | None = None


@dataclass(frozen=True, slots=True)
class VectorStoreConfigData:
    dim: int = 384
    index_path: str = "./data/indices/default"
    metric: str = "l2"
    max_chunks: int = 100_000
    max_document_size: int = 10_485_760


@dataclass(frozen=True, slots=True)
class StorageConfigData:
    db_path: str = "./data/storage.db"


@dataclass(frozen=True, slots=True)
class RerankerConfigData:
    model: str = "rerank-multilingual-v3.0"
    api_base: str = "https://api.cohere.com"
    api_key: str | None = None
    timeout: float = 30.0
    threshold: float = 0.3
