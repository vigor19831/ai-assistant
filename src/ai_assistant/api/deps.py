"""API dependencies — AppState, get_state, MetricsMiddleware."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware

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
from ai_assistant.api.security import get_expected_api_key
from ai_assistant.core import metrics as _metrics_module
from ai_assistant.core import registry as _registry
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.ports.initializable import IInitializable
from ai_assistant.core.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
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
    "clear_state",
    "get_current_metrics",
    "get_state",
    "init_adapters",
    "MetricsMiddleware",
    "set_state",
]

_logger = get_logger("deps")

_state: AppState | None = None
_init_lock = asyncio.Lock()
_init_event = asyncio.Event()


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


def set_state(state: AppState) -> None:
    """Set global state (intended for tests and CLI bootstrapping)."""
    global _state
    _state = state
    _init_event.set()


def clear_state() -> None:
    """Clear global state (intended for test teardown)."""
    global _state
    _state = None
    _init_event.clear()


async def init_adapters(config: AppConfig | AppState) -> AppState:
    """Initialize all adapters via Registry and return populated AppState."""
    global _state

    def _should_use_cache() -> bool:
        if _state is None or not _init_event.is_set():
            return False
        if isinstance(config, AppState):
            return config is _state
        return _state.config is config

    if _should_use_cache():
        assert _state is not None
        return _state

    async with _init_lock:
        if _should_use_cache():
            assert _state is not None
            return _state

        try:
            if isinstance(config, AppState):
                state = config
                cfg = state.config
            else:
                cfg = config
                state = AppState(config=cfg)

            # --- Security: reconfigure global limiter from loaded config ---
            from ai_assistant import api

            api.security.limiter.reset(cfg.security.rate_limit)
            # If config has an API key and no env override is set, promote it
            if cfg.security.api_key and get_expected_api_key() is None:
                api.security.set_api_key(cfg.security.api_key)

            state.tool_registry = ToolRegistry()

            try:
                tool = _registry.create("tool", "calculator", cfg)
                state.tool_registry.register(tool)
            except Exception:
                _logger.exception("Calculator tool not available")

            state.chunker = _registry.create(
                "chunker", cfg.chunker.provider, cfg.chunker
            )
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
                state.long_term_memory = _registry.create(
                    "memory", "sqlite", cfg.storage
                )
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
                state.vision = _registry.create(
                    "vision", cfg.vision.provider, cfg.vision
                )

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
            _state = state
            _init_event.set()
            return state
        except Exception:
            _state = None
            _init_event.clear()
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


def get_state(request: Any = None) -> AppState:
    """Get initialized app state.

    If *request* is provided and the FastAPI app state has an ``app_state``
    attribute, return it.  Otherwise fall back to the global singleton.
    Raises RuntimeError if the singleton has not been initialized.
    """
    if request is not None:
        fastapi_state = request.app.state
        app_state = getattr(fastapi_state, "app_state", None)
        if isinstance(app_state, AppState):
            return app_state
    if _state is None or not _init_event.is_set():
        raise RuntimeError("State not initialized. Call init_adapters() first.")
    return _state


def get_current_metrics() -> dict[str, Any]:
    """Get metrics collected for the current request."""
    return _metrics_module.get_current_metrics()


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
        _metrics_module.get_metrics_logger().log(metrics)
        return response
