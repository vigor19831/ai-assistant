"""API dependencies — AppState, get_state."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from starlette.requests import Request  # noqa: TC002  # FastAPI DI requires runtime

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import AppConfig, RAGStep
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
    StorageConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.features.chat.manager import ChatManager

if TYPE_CHECKING:
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.ports import (
        ILLM,
        IChatStorage,
        IChunker,
        IEmbedder,
        IReranker,
        IVectorStore,
    )

__all__ = [
    "AppState",
    "InitializedAppState",
    "get_state",
    "init_adapters",
]

_logger = get_logger("deps")


@dataclass
class AppState:
    """Application state container — pre-initialization, mutable for tests."""

    config: AppConfig
    llm: ILLM | None = None
    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    chunker: IChunker | None = None
    reranker: IReranker | None = None
    pipeline: RAGPipeline | None = None
    storage: IChatStorage | None = None
    chat_manager: ChatManager | None = None


@dataclass
class InitializedAppState:
    """Runtime application state — core adapters are guaranteed present."""

    config: AppConfig
    llm: ILLM
    embedder: IEmbedder
    vector_store: IVectorStore
    pipeline: RAGPipeline
    storage: IChatStorage
    chunker: IChunker
    chat_manager: ChatManager
    reranker: IReranker


# ---------------------------------------------------------------------------
# Explicit step map — replaces mutable @step registry
# ---------------------------------------------------------------------------

_STEP_MAP: dict[RAGStep, Callable[[PipelineData], Awaitable[PipelineData]]] = {
    RAGStep(k): v for k, v in STEP_REGISTRY.items() if k in {m.value for m in RAGStep}
}


def _build_step_funcs(
    cfg: AppConfig,
    stop_at: RAGStep | None = None,
) -> list[Callable[[PipelineData], Awaitable[PipelineData]]]:
    """Build pipeline step functions. Stops before *stop_at* if provided."""
    step_funcs: list[Callable[[PipelineData], Awaitable[PipelineData]]] = []
    for step in cfg.rag.steps:
        if stop_at is not None and step == stop_at:
            break
        func = _STEP_MAP.get(step)
        if func is None:
            raise ValueError(f"Unknown step: {step}")
        step_funcs.append(func)
    return step_funcs


# ---------------------------------------------------------------------------
# Config conversion — Pydantic -> dataclass for port contracts
# ---------------------------------------------------------------------------


def _chunker_data(cfg: AppConfig) -> ChunkerConfigData:
    c = cfg.chunker
    return ChunkerConfigData(
        chunk_size=c.chunk_size,
        chunk_overlap=c.chunk_overlap,
    )


def _embedder_data(cfg: AppConfig) -> EmbedderConfigData:
    c = cfg.embedder
    return EmbedderConfigData(
        model=c.model,
        api_base=c.api_base,
        api_key=c.api_key,
        dim=c.dim,
        timeout=c.timeout,
        connect_timeout=c.connect_timeout,
        n_gpu_layers=c.n_gpu_layers,
        n_batch=c.n_batch,
        n_ubatch=c.n_ubatch,
        mmap=c.mmap,
        mlock=c.mlock,
    )


def _llm_data(cfg: AppConfig) -> LLMConfigData:
    c = cfg.llm
    return LLMConfigData(
        model=c.model,
        api_base=c.api_base,
        api_key=c.api_key,
        max_tokens=c.max_tokens,
        temperature=c.temperature,
        timeout=c.timeout,
        connect_timeout=c.connect_timeout,
        server_context_size=c.server_context_size,
        top_p=c.top_p,
        top_k=c.top_k,
        min_p=c.min_p,
        repeat_penalty=c.repeat_penalty,
        presence_penalty=c.presence_penalty,
        frequency_penalty=c.frequency_penalty,
        stop_sequences=tuple(c.stop_sequences),
        system_message=c.system_message,
        available_models=tuple(c.available_models),
        n_gpu_layers=c.n_gpu_layers,
        n_batch=c.n_batch,
        n_ubatch=c.n_ubatch,
        mmap=c.mmap,
        mlock=c.mlock,
    )


def _vector_store_data(cfg: AppConfig) -> VectorStoreConfigData:
    c = cfg.vector_store
    return VectorStoreConfigData(
        dim=c.dim,
        index_path=c.index_path,
        metric=c.metric,
        max_chunks=c.max_chunks,
        max_document_size=c.max_document_size,
    )


def _storage_data(cfg: AppConfig) -> StorageConfigData:
    c = cfg.storage
    return StorageConfigData(db_path=c.db_path)


def _reranker_data(cfg: AppConfig) -> RerankerConfigData | None:
    if cfg.reranker is None or cfg.reranker.provider is None:
        return None
    c = cfg.reranker
    return RerankerConfigData(
        model=c.model,
        api_base=c.api_base,
        api_key=c.api_key,
        timeout=c.timeout,
        threshold=c.threshold,
    )


# ---------------------------------------------------------------------------
# Adapter initialization
# ---------------------------------------------------------------------------


async def init_adapters(config: AppConfig) -> InitializedAppState:
    """Initialize all adapters via factory and return populated InitializedAppState."""
    state = AppState(config=config)
    cfg = config

    state.chunker = create_adapter("chunker", cfg.chunker.provider, _chunker_data(cfg))
    state.embedder = create_adapter(
        "embedder", cfg.embedder.provider, _embedder_data(cfg)
    )
    state.llm = create_adapter("llm", cfg.llm.provider, _llm_data(cfg))
    state.vector_store = create_adapter(
        "vector_store",
        cfg.vector_store.provider,
        _vector_store_data(cfg),
    )

    reranker_cfg = _reranker_data(cfg)
    if reranker_cfg is not None and cfg.reranker.provider is not None:
        state.reranker = create_adapter("reranker", cfg.reranker.provider, reranker_cfg)
    else:
        state.reranker = create_adapter("reranker", "null", RerankerConfigData())

    try:
        state.storage = create_adapter(
            "storage", cfg.storage.provider, _storage_data(cfg)
        )
    except (ValueError, ImportError):
        _logger.exception(
            "Storage adapter not available",
            extra={"provider": cfg.storage.provider},
        )

    if state.storage is not None:
        await state.storage.init_db()

    step_funcs = _build_step_funcs(cfg)
    state.pipeline = RAGPipeline(step_funcs)

    retrieval_funcs = _build_step_funcs(cfg, stop_at=RAGStep.GENERATE)
    retrieval_pipeline = RAGPipeline(retrieval_funcs) if retrieval_funcs else None

    state.chat_manager = ChatManager(
        llm=state.llm,
        storage=state.storage,
        history_limit=cfg.chat.history_limit,
        max_context_tokens=cfg.chat.max_context_tokens,
        tokenizer_model=cfg.chat.tokenizer_model,
        embedder=state.embedder,
        vector_store=state.vector_store,
        reranker=state.reranker,
        pipeline=retrieval_pipeline,
        namespaces=cfg.namespaces,
        prompt_version=cfg.rag.prompt_version,
        top_k=cfg.rag.top_k,
        token_margin_min=cfg.rag.token_margin_min,
        token_margin_pct=cfg.rag.token_margin_pct,
    )

    if state.llm is None:
        raise RuntimeError("LLM adapter failed to initialize")
    if state.embedder is None:
        raise RuntimeError("Embedder adapter failed to initialize")
    if state.vector_store is None:
        raise RuntimeError("Vector store adapter failed to initialize")
    if state.pipeline is None:
        raise RuntimeError("Pipeline failed to initialize")
    if state.storage is None:
        raise RuntimeError("Storage adapter failed to initialize")
    if state.chunker is None:
        raise RuntimeError("Chunker adapter failed to initialize")
    if state.chat_manager is None:
        raise RuntimeError("Chat manager failed to initialize")
    return InitializedAppState(
        config=cfg,
        llm=state.llm,
        embedder=state.embedder,
        vector_store=state.vector_store,
        pipeline=state.pipeline,
        storage=state.storage,
        chunker=state.chunker,
        reranker=state.reranker,
        chat_manager=state.chat_manager,
    )


def get_state(request: Request) -> InitializedAppState:
    """Get initialized app state. Raises RuntimeError if missing."""
    app_state = getattr(request.app.state, "app_state", None)
    if app_state is None:
        raise RuntimeError("State not initialized")
    return app_state
