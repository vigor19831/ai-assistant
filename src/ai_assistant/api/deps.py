"""API dependencies — AppState, get_state, MetricsMiddleware."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request  # noqa: TC002

# Eager-load adapters to trigger @register side-effects
import ai_assistant.adapters.chunker_simple  # noqa: F401
import ai_assistant.adapters.embedder_mock  # noqa: F401
import ai_assistant.adapters.embedder_openai_compatible  # noqa: F401
import ai_assistant.adapters.llm_mock  # noqa: F401
import ai_assistant.adapters.llm_openai_compatible  # noqa: F401
import ai_assistant.adapters.memory_sqlite  # noqa: F401
import ai_assistant.adapters.reranker_api  # noqa: F401
import ai_assistant.adapters.reranker_dummy  # noqa: F401
import ai_assistant.adapters.storage_sqlite  # noqa: F401
import ai_assistant.adapters.tools_calculator  # noqa: F401
import ai_assistant.adapters.vector_store_faiss  # noqa: F401
import ai_assistant.adapters.vector_store_memory  # noqa: F401
import ai_assistant.adapters.vision_clip_local  # noqa: F401
import ai_assistant.adapters.voice_piper  # noqa: F401
import ai_assistant.adapters.voice_whisper_local  # noqa: F401
import ai_assistant.adapters.voice_whispercpp  # noqa: F401
from ai_assistant.core import registry as _registry
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import get_current_metrics
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.ports.initializable import IInitializable
from ai_assistant.core.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.responses import Response

    from ai_assistant.core.config import AppConfig
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.ports import (
        ILLM,
        IChatStorage,
        IChunker,
        IEmbedder,
        ILongTermMemory,
        IReranker,
        IVectorStore,
        IVisionProcessor,
        IVoiceRecognizer,
        IVoiceSynthesizer,
    )

__all__ = [
    "AppState",
    "get_current_metrics",
    "get_state",
    "init_adapters",
    "MetricsMiddleware",
]

_logger = get_logger("deps")


@dataclass(slots=True)
class AppState:
    """Application state container — initialized once at startup."""

    config: AppConfig
    llm: ILLM | None = None
    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    chunker: IChunker | None = None
    reranker: IReranker | None = None
    pipeline: RAGPipeline | None = None
    storage: IChatStorage | None = None
    voice_recognizer: IVoiceRecognizer | None = None
    voice_synthesizer: IVoiceSynthesizer | None = None
    vision: IVisionProcessor | None = None
    tool_registry: ToolRegistry | None = None
    long_term_memory: ILongTermMemory | None = None
    chat_manager: Any | None = None
    limiter: Any | None = None
    metrics: Any | None = None


async def init_adapters(config: AppConfig | AppState) -> AppState:
    """Initialize all adapters via Registry and return populated AppState."""
    if isinstance(config, AppState):
        if config.pipeline is not None:
            # Already initialized — idempotent
            return config
        state = config
        cfg = state.config
    else:
        cfg = config
        state = AppState(config=cfg)

    try:
        state.tool_registry = ToolRegistry()

        try:
            tool = _registry.create("tool", "calculator", cfg)
            state.tool_registry.register(tool)
        except Exception:
            _logger.exception("Calculator tool not available")

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

        state.storage = None
        try:
            state.storage = _registry.create(
                "storage", cfg.storage.provider, cfg.storage
            )
        except Exception:
            _logger.exception(
                "Storage adapter '%s' not available",
                cfg.storage.provider,
            )
            state.storage = None

        if state.storage is not None and isinstance(state.storage, IInitializable):
            await state.storage.init_db()

        try:
            state.long_term_memory = _registry.create("memory", "sqlite", cfg.storage)
        except Exception:
            _logger.exception("Long-term memory not available")
            state.long_term_memory = None

        if state.long_term_memory is not None and isinstance(
            state.long_term_memory, IInitializable
        ):
            await state.long_term_memory.init_db()

        if cfg.voice.enabled:
            state.voice_recognizer = _registry.create(
                "voice_recognizer",
                cfg.voice.recognizer_provider,
                cfg.voice,
            )
            state.voice_synthesizer = _registry.create(
                "voice_synthesizer",
                cfg.voice.synthesizer_provider,
                cfg.voice,
            )

        if cfg.vision.enabled:
            state.vision = _registry.create("vision", cfg.vision.provider, cfg.vision)

        from ai_assistant.features.chat.manager import ChatManager

        state.chat_manager = ChatManager(
            llm=state.llm,
            voice_recognizer=state.voice_recognizer,
            vision=state.vision,
            storage=state.storage,
            history_limit=cfg.chat.history_limit,
            max_context_tokens=cfg.chat.max_context_tokens,
            tokenizer_model=cfg.chat.tokenizer_model,
            tool_registry=state.tool_registry,
            embedder=state.embedder,
            vector_store=state.vector_store,
            reranker=state.reranker,
        )

        step_funcs = _build_step_funcs(cfg, state)
        state.pipeline = RAGPipeline(step_funcs)
        return state
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


def get_state(request: Request) -> AppState:
    """Get initialized app state from the FastAPI application state.

    Raises RuntimeError if app_state has not been set on the application.
    """
    app_state = getattr(request.app.state, "app_state", None)
    if isinstance(app_state, AppState):
        return app_state
    raise RuntimeError("State not initialized")


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request latency and token metrics."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start) * 1000)
        metrics = get_current_metrics()
        metrics["endpoint"] = request.url.path
        metrics["status_code"] = response.status_code
        metrics["latency_ms"] = latency_ms

        state = getattr(request.app.state, "app_state", None)
        if isinstance(state, AppState) and state.metrics is not None:
            state.metrics.log(metrics)
        return response
