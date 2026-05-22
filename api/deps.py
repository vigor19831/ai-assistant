"""API dependencies — AppState, get_state, MetricsMiddleware."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware

# ── Eager-load adapters to trigger @register side-effects ──
import adapters.chunker_simple  # noqa: F401
import adapters.embedder_mock  # noqa: F401
import adapters.embedder_openai_compatible  # noqa: F401
import adapters.llm_mock  # noqa: F401
import adapters.llm_openai_compatible  # noqa: F401
import adapters.memory_sqlite  # noqa: F401
import adapters.reranker_api  # noqa: F401
import adapters.reranker_dummy  # noqa: F401
import adapters.storage_sqlite  # noqa: F401
import adapters.tools_calculator  # noqa: F401
import adapters.vector_store_faiss  # noqa: F401
import adapters.vector_store_memory  # noqa: F401
import adapters.vision_clip_local  # noqa: F401
import adapters.voice_piper  # noqa: F401
import adapters.voice_whisper_local  # noqa: F401
import adapters.voice_whispercpp  # noqa: F401
from core.config import AppConfig
from core.metrics import get_metrics_logger
from core.pipeline import RAGPipeline
from core.registry import create as registry_create
from core.tool_registry import ToolRegistry
from pipeline.decorators import get_step


@dataclass
class AppState:
    """Application state container — initialized once at startup."""

    config: AppConfig
    llm: Any = None
    embedder: Any = None
    vector_store: Any = None
    chunker: Any = None
    reranker: Any = None
    pipeline: Any = None
    storage: Any = None
    voice_recognizer: Any = None
    voice_synthesizer: Any = None
    vision: Any = None
    tool_registry: Any = None
    long_term_memory: Any = None


# Global state — initialized exactly once via asyncio.Event
_state: AppState | None = None
_init_event = asyncio.Event()
_initializing = False


async def init_adapters(config: AppConfig | AppState) -> AppState:
    """Initialize all adapters via Registry and return populated AppState."""
    global _state, _initializing

    # Fast path
    if _init_event.is_set() and _state is not None:
        return _state

    # Another coroutine is initializing — wait for it
    if _initializing:
        await _init_event.wait()
        if _state is not None:
            return _state

    _initializing = True
    # Reset event if it was set from a previous (failed) run
    if _init_event.is_set():
        _init_event.clear()

    try:
        # Normalize input: tests may pass AppState, production passes AppConfig
        if isinstance(config, AppState):
            state = config
            cfg = state.config
        else:
            cfg = config
            state = AppState(config=cfg)

        if not isinstance(config, AppState):
            state = AppState(config=cfg)
        state.tool_registry = ToolRegistry()

        try:
            tool = registry_create("tool", "calculator", cfg)
            state.tool_registry.register(tool)
        except Exception:
            pass

        state.chunker = registry_create("chunker", cfg.chunker.provider, cfg.chunker)
        state.embedder = registry_create(
            "embedder", cfg.embedder.provider, cfg.embedder
        )
        state.llm = registry_create("llm", cfg.llm.provider, cfg.llm)
        state.vector_store = registry_create(
            "vector_store", cfg.vector_store.provider, cfg.vector_store
        )

        if getattr(cfg, "reranker", None) and getattr(cfg.reranker, "provider", None):
            try:
                state.reranker = registry_create(
                    "reranker", cfg.reranker.provider, cfg.reranker
                )
            except ValueError:
                pass

        try:
            state.storage = registry_create(
                "storage", cfg.storage.provider, cfg.storage
            )
        except ValueError as e:
            import logging

            logging.getLogger("ai_assistant.deps").warning(
                "Storage adapter '%s' not available: %s", cfg.storage.provider, e
            )
            state.storage = None

        if state.storage is not None and hasattr(state.storage, "init_db"):
            await state.storage.init_db()

        try:
            state.long_term_memory = registry_create("memory", "sqlite", cfg.storage)
        except Exception as e:
            import logging

            logging.getLogger("ai_assistant.deps").warning(
                "Long-term memory not available: %s", e
            )
            state.long_term_memory = None

        if state.long_term_memory is not None and hasattr(
            state.long_term_memory, "init_db"
        ):
            await state.long_term_memory.init_db()

        if cfg.voice.enabled:
            state.voice_recognizer = registry_create(
                "voice_recognizer", cfg.voice.recognizer_provider, cfg.voice
            )
            state.voice_synthesizer = registry_create(
                "voice_synthesizer", cfg.voice.synthesizer_provider, cfg.voice
            )

        if cfg.vision.enabled:
            state.vision = registry_create("vision", cfg.vision.provider, cfg.vision)

        index_path = getattr(cfg.vector_store, "index_path", None)
        if index_path:
            try:
                namespaces = await state.vector_store.list_namespaces(index_path)
                for ns in namespaces:
                    await state.vector_store.load(index_path, namespace=ns)
            except Exception:
                try:
                    await state.vector_store.load(index_path, namespace="default")
                except Exception:
                    pass

        step_funcs: list[Any] = []
        for name in cfg.rag.steps:
            func = get_step(name)
            if name == "embed_query":
                step_funcs.append(
                    lambda d, e=state.embedder, _f=func: _f(d, embedder=e)
                )
            elif name == "retrieve":
                step_funcs.append(
                    lambda d, vs=state.vector_store, _f=func: _f(d, vector_store=vs)
                )
            elif name == "rerank":
                step_funcs.append(
                    lambda d, r=state.reranker, _f=func: _f(d, reranker=r)
                )
            elif name == "generate":
                step_funcs.append(
                    lambda d, llm=state.llm, tr=state.tool_registry, _f=func: _f(
                        d, llm=llm, tool_registry=tr
                    )
                )
            else:
                step_funcs.append(func)

        state.pipeline = RAGPipeline(step_funcs)
        _state = state
        _init_event.set()
        return state
    except Exception:
        _state = None
        _init_event.clear()
        raise
    finally:
        _initializing = False


def get_state(request: Any = None) -> AppState:
    """Get initialized app state."""
    if request is not None and hasattr(request.app.state, "app_state"):
        return request.app.state.app_state
    if not _init_event.is_set() or _state is None:
        raise RuntimeError("State not initialized. Call init_adapters() first.")
    return _state


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request latency and token metrics."""

    async def dispatch(self, request, call_next):
        import time

        from core.metrics import get_current_metrics

        start = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start) * 1000)
        metrics = get_current_metrics()
        metrics["endpoint"] = request.url.path
        metrics["status_code"] = response.status_code
        metrics["latency_ms"] = latency_ms
        get_metrics_logger().log(metrics)
        return response


def get_current_metrics() -> dict[str, Any]:
    """Get metrics collected for the current request."""
    from core.metrics import get_current_metrics as _get_metrics

    return _get_metrics()
