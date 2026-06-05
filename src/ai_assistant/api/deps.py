"""API dependencies — AppState, get_state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.requests import Request  # noqa: TC002

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import AppConfig, RAGStep
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.features.chat.manager import ChatManager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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
    limiter: Any | None = None


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
    reranker: IReranker | None = None
    limiter: Any | None = None


# ---------------------------------------------------------------------------
# Explicit step map — replaces mutable @step registry
# ---------------------------------------------------------------------------

_STEP_MAP: dict[RAGStep, Callable[[PipelineData], Awaitable[PipelineData]]] = {
    RAGStep(k): v for k, v in STEP_REGISTRY.items() if k in {m.value for m in RAGStep}
}


def _build_step_funcs(
    cfg: AppConfig, state: AppState
) -> list[Callable[[PipelineData], Awaitable[PipelineData]]]:
    """Build pipeline step functions. Dependencies injected via metadata."""
    step_funcs: list[Callable[[PipelineData], Awaitable[PipelineData]]] = []
    for step in cfg.rag.steps:
        func = _STEP_MAP.get(step)
        if func is None:
            raise ValueError(f"Unknown step: {step}")
        step_funcs.append(func)
    return step_funcs


# ---------------------------------------------------------------------------
# Adapter initialization
# ---------------------------------------------------------------------------


def _rehydrate_state(state: AppState) -> InitializedAppState:
    """Convert already-initialized AppState into InitializedAppState."""
    if state.pipeline is None:
        raise ValueError("AppState is not initialized")
    if state.llm is None:
        raise RuntimeError("LLM adapter failed to initialize")
    if state.embedder is None:
        raise RuntimeError("Embedder adapter failed to initialize")
    if state.vector_store is None:
        raise RuntimeError("Vector store adapter failed to initialize")
    if state.storage is None:
        raise RuntimeError("Storage adapter failed to initialize")
    if state.chunker is None:
        raise RuntimeError("Chunker adapter failed to initialize")
    if state.chat_manager is None:
        raise RuntimeError("Chat manager failed to initialize")
    return InitializedAppState(
        config=state.config,
        llm=state.llm,
        embedder=state.embedder,
        vector_store=state.vector_store,
        pipeline=state.pipeline,
        storage=state.storage,
        chunker=state.chunker,
        reranker=state.reranker,
        chat_manager=state.chat_manager,
        limiter=state.limiter,
    )


async def init_adapters(config: AppConfig) -> InitializedAppState:
    """Initialize all adapters via factory and return populated InitializedAppState."""
    state = AppState(config=config)
    cfg = config

    state.chunker = create_adapter("chunker", cfg.chunker.provider, cfg.chunker)
    state.embedder = create_adapter("embedder", cfg.embedder.provider, cfg.embedder)
    state.llm = create_adapter("llm", cfg.llm.provider, cfg.llm)
    state.vector_store = create_adapter(
        "vector_store",
        cfg.vector_store.provider,
        cfg.vector_store,
    )

    if cfg.reranker is not None and cfg.reranker.provider is not None:
        try:
            state.reranker = create_adapter(
                "reranker",
                cfg.reranker.provider,
                cfg.reranker,
            )
        except ValueError:
            _logger.exception(
                "Reranker '%s' not available",
                cfg.reranker.provider,
            )

    try:
        state.storage = create_adapter("storage", cfg.storage.provider, cfg.storage)
    except (ValueError, ImportError):
        _logger.exception(
            "Storage adapter '%s' not available",
            cfg.storage.provider,
        )

    if state.storage is not None:
        await state.storage.init_db()

    step_funcs = _build_step_funcs(cfg, state)
    state.pipeline = RAGPipeline(step_funcs)

    # Build retrieval sub-pipeline for ChatManager (all steps before generate)
    retrieval_funcs: list[Callable[[PipelineData], Awaitable[PipelineData]]] = []
    for step in cfg.rag.steps:
        if step == RAGStep.GENERATE:
            break
        func = _STEP_MAP.get(step)
        if func is None:
            raise ValueError(f"Unknown step: {step}")
        retrieval_funcs.append(func)
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
        limiter=state.limiter,
    )


def get_state(request: Request) -> InitializedAppState:
    """Get initialized app state from the FastAPI application state.

    Raises RuntimeError if app_state has not been set on the application.
    """
    app_state = getattr(request.app.state, "app_state", None)
    if app_state is not None:
        return app_state  # type: ignore[return-value]
    raise RuntimeError("State not initialized")
