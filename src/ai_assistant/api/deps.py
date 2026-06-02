"""API dependencies — AppState, get_state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.requests import Request  # noqa: TC002

# Eager-load adapters to trigger @register side-effects
import ai_assistant.adapters.chunker_simple  # noqa: F401
import ai_assistant.adapters.embedder_mock  # noqa: F401
import ai_assistant.adapters.embedder_openai_compatible  # noqa: F401
import ai_assistant.adapters.llm_mock  # noqa: F401
import ai_assistant.adapters.llm_openai_compatible  # noqa: F401
import ai_assistant.adapters.vector_store_faiss  # noqa: F401
import ai_assistant.adapters.vector_store_memory  # noqa: F401
from ai_assistant.core import registry as _registry
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.ports.initializable import IInitializable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.config import AppConfig
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
    chat_manager: Any | None = None
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
    chunker: IChunker | None = None
    reranker: IReranker | None = None
    chat_manager: Any | None = None
    limiter: Any | None = None


async def init_adapters(config: AppConfig | AppState) -> InitializedAppState:
    """Initialize all adapters via Registry and return populated InitializedAppState."""
    if isinstance(config, AppState):
        if config.pipeline is not None:
            # Already initialized — idempotent
            # Convert to InitializedAppState to satisfy type contract
            return InitializedAppState(
                config=config.config,
                llm=config.llm,  # type: ignore[arg-type]
                embedder=config.embedder,  # type: ignore[arg-type]
                vector_store=config.vector_store,  # type: ignore[arg-type]
                pipeline=config.pipeline,  # type: ignore[arg-type]
                storage=config.storage,  # type: ignore[arg-type]
                chunker=config.chunker,
                reranker=config.reranker,
                chat_manager=config.chat_manager,
                limiter=config.limiter,
            )
        state = config
        cfg = state.config
    else:
        cfg = config
        state = AppState(config=cfg)

    try:
        state.chunker = _registry.create("chunker", cfg.chunker.provider, cfg.chunker)
        state.embedder = _registry.create(
            "embedder", cfg.embedder.provider, cfg.embedder
        )
        state.llm = _registry.create("llm", cfg.llm.provider, cfg.llm)
        state.vector_store = _registry.create(
            "vector_store",
            cfg.vector_store.provider,
            cfg.vector_store,
        )

        if cfg.reranker is not None and cfg.reranker.provider is not None:
            try:
                state.reranker = _registry.create(
                    "reranker",
                    cfg.reranker.provider,
                    cfg.reranker,
                )
            except ValueError:
                _logger.exception(
                    "Reranker '%s' not available",
                    cfg.reranker.provider,
                )

        if cfg.storage.provider in _registry.list_adapters("storage"):
            try:
                state.storage = _registry.create(
                    "storage", cfg.storage.provider, cfg.storage
                )
            except ImportError:
                _logger.exception(
                    "Storage adapter '%s' not available",
                    cfg.storage.provider,
                )

        if state.storage is not None and isinstance(state.storage, IInitializable):
            await state.storage.init_db()

        step_funcs = _build_step_funcs(cfg, state)
        state.pipeline = RAGPipeline(step_funcs)

        # Build retrieval sub-pipeline for ChatManager (all steps before generate)
        from ai_assistant.pipeline.decorators import get_step

        retrieval_funcs: list[Callable[[PipelineData], Awaitable[PipelineData]]] = []
        for name in cfg.rag.steps:
            if name == "generate":
                break
            retrieval_funcs.append(get_step(name))
        retrieval_pipeline = RAGPipeline(retrieval_funcs) if retrieval_funcs else None

        from ai_assistant.features.chat.manager import ChatManager

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
        )

        return InitializedAppState(
            config=cfg,
            llm=state.llm,  # type: ignore[arg-type]
            embedder=state.embedder,  # type: ignore[arg-type]
            vector_store=state.vector_store,  # type: ignore[arg-type]
            pipeline=state.pipeline,  # type: ignore[arg-type]
            storage=state.storage,  # type: ignore[arg-type]
            chunker=state.chunker,
            reranker=state.reranker,
            chat_manager=state.chat_manager,
            limiter=state.limiter,
        )
    except Exception:
        raise


def _build_step_funcs(
    cfg: AppConfig, state: AppState
) -> list[Callable[[PipelineData], Awaitable[PipelineData]]]:
    """Build pipeline step functions. Dependencies injected via metadata."""
    from ai_assistant.pipeline.decorators import get_step

    step_funcs: list[Callable[[PipelineData], Awaitable[PipelineData]]] = []
    for name in cfg.rag.steps:
        func = get_step(name)
        step_funcs.append(func)
    return step_funcs


def get_state(request: Request) -> InitializedAppState:
    """Get initialized app state from the FastAPI application state.

    Raises RuntimeError if app_state has not been set on the application.
    """
    app_state = getattr(request.app.state, "app_state", None)
    if isinstance(app_state, InitializedAppState):
        return app_state
    raise RuntimeError("State not initialized")
