"""Immutable dataclass configurations for adapter port contracts.

Each dataclass mirrors a subset of the Pydantic AppConfig models
(core/config.py) as stdlib-only frozen dataclasses. This keeps
core/ports/ free of any Pydantic dependency and guarantees immutability.

All fields have sensible defaults matching the production config defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkerConfigData:
    """Configuration for document chunking adapters.

    Attributes:
        chunk_size: Target size of each chunk in characters.
        chunk_overlap: Number of overlapping characters between chunks.
    """

    chunk_size: int = 512
    chunk_overlap: int = 50


@dataclass(frozen=True, slots=True)
class EmbedderConfigData:
    """Configuration for text embedding adapters.

    Attributes:
        model: Model identifier on the embedding server.
        api_base: Base URL of the OpenAI-compatible embedding API.
        api_key: Optional API key for authentication.
        dim: Embedding vector dimension (must match vector_store.dim).
        timeout: Total request timeout in seconds.
        connect_timeout: TCP connection timeout in seconds.
        n_gpu_layers: Number of layers to offload to GPU (0 = CPU, 99 = all).
    """

    model: str = "text-embedding-3-small"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0
    connect_timeout: float | None = None
    n_gpu_layers: int = 0


@dataclass(frozen=True, slots=True)
class LLMConfigData:
    """Configuration for language model adapters.

    Attributes:
        model: Model identifier on the LLM server.
        api_base: Base URL of the OpenAI-compatible LLM API.
        api_key: Optional API key for authentication.
        max_tokens: Maximum tokens to generate per completion.
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
        timeout: Total request timeout in seconds.
        connect_timeout: TCP connection timeout in seconds.
        server_context_size: Context window size advertised by the server.
        top_p: Nucleus sampling probability threshold.
        stop_sequences: Sequences that stop generation.
        system_message: Optional system prompt override.
        available_models: List of models available on this server.
        n_gpu_layers: Number of layers to offload to GPU (0 = CPU, 99 = all).
    """

    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout: float = 300.0
    connect_timeout: float | None = None
    server_context_size: int | None = None
    top_p: float = 1.0
    stop_sequences: tuple[str, ...] = ()
    system_message: str | None = None
    available_models: tuple[str, ...] = ()
    n_gpu_layers: int = 99


@dataclass(frozen=True, slots=True)
class VectorStoreConfigData:
    """Configuration for vector store adapters.

    Attributes:
        dim: Embedding vector dimension (must match embedder.dim).
        index_path: Directory path for persistent index storage.
        metric: Distance metric ("l2", "cosine", "ip").
        max_chunks: Maximum number of chunks per namespace.
        max_document_size: Maximum document size in bytes.
    """

    dim: int = 384
    index_path: str = "./data/indices/default"
    metric: str = "l2"
    max_chunks: int = 100_000
    max_document_size: int = 10_485_760


@dataclass(frozen=True, slots=True)
class StorageConfigData:
    """Configuration for persistent storage adapters.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    db_path: str = "./data/storage.db"


@dataclass(frozen=True, slots=True)
class RerankerConfigData:
    """Configuration for reranker adapters.

    Attributes:
        model: Model identifier for the reranker endpoint.
        api_base: Base URL of the reranker API.
        api_key: Optional API key for authentication.
        timeout: Total request timeout in seconds.
        n_gpu_layers: Layer offload for the local reranker server
            (0 = CPU). Read by run_servers.py, not by the adapter.
    """

    model: str = "rerank-multilingual-v3.0"
    api_base: str = "https://api.cohere.com"
    api_key: str | None = None
    timeout: float = 30.0
    n_gpu_layers: int = 0


@dataclass(frozen=True, slots=True)
class TokenizerConfigData:
    """Configuration for tokenizer adapters.

    Attributes:
        provider: Adapter identifier ("tiktoken", "char_fallback").
        local_dir: Directory containing local HF tokenizer.json files.
        model_name: Tokenizer model/encoding identifier.
    """

    provider: str = "tiktoken"
    local_dir: str = "./data/tokenizers"
    model_name: str = "cl100k_base"


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    """Configuration for LLM sampling parameters.

    Attributes:
        max_tokens: Maximum tokens to generate per completion.
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
        top_p: Nucleus sampling probability threshold.
        stop_sequences: Sequences that stop generation.
    """

    max_tokens: int = 1024
    temperature: float = 0.0
    top_p: float = 1.0
    stop_sequences: tuple[str, ...] = ()
