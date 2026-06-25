"""API dependencies — AppState, get_state."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from starlette.requests import Request  # noqa: TC002  # FastAPI DI requires runtime

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import AppConfig
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
    StorageConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.logger import get_logger

if TYPE_CHECKING:
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
    "RAGState",
    "get_state",
    "init_adapters",
]

_logger = get_logger("deps")


def _to_float(value: object, default: float = 0.0) -> float:
    """Safely convert a value to float with explicit narrowing."""
    if isinstance(value, (int, float)):
        return float(value)
    return default


@dataclass
class RAGState:
    """Explicit per-instance RAG background task state.

    Replaces module-level globals to eliminate shared mutable state
    across tests and application instances.
    """

    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    _tasks: dict[str, asyncio.Task[dict[str, object]]] = field(default_factory=dict)
    _status: dict[str, dict[str, object]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    STATUS_TTL_SECONDS: int = field(default=3600, repr=False)
    STATUS_MAX_ENTRIES: int = field(default=1000, repr=False)

    # ------------------------------------------------------------------
    # Public lifecycle API — all mutations go through these methods
    # ------------------------------------------------------------------

    async def start_task(self, task_id: str) -> None:
        """Atomically register a running task."""
        await self.cleanup_status()
        async with self._lock:
            self._status[task_id] = {
                "status": "running",
                "started_at": time.time(),
            }

    async def register_task(self, task_id: str, task: asyncio.Task[dict[str, object]]) -> None:
        """Atomically store the asyncio.Task reference."""
        async with self._lock:
            self._tasks[task_id] = task

    async def complete_task(self, task_id: str, result: dict[str, object]) -> None:
        """Atomically mark task completed and remove from active tasks."""
        async with self._lock:
            self._status[task_id] = {
                "status": "completed",
                "result": result,
                "finished_at": time.time(),
            }
            self._tasks.pop(task_id, None)

    async def fail_task(self, task_id: str, error: str) -> None:
        """Atomically mark task failed and remove from active tasks."""
        async with self._lock:
            self._status[task_id] = {
                "status": "failed",
                "error": error,
                "finished_at": time.time(),
            }
            self._tasks.pop(task_id, None)

    async def get_status(self, task_id: str) -> dict[str, object] | None:
        """Return a shallow copy of status for the given task, or None."""
        async with self._lock:
            info = self._status.get(task_id)
            return dict(info) if info is not None else None

    async def cleanup_status(self) -> None:
        """Remove expired entries and enforce max size cap on status."""
        async with self._lock:
            now = time.time()

            expired: list[str] = []
            for tid, info in self._status.items():
                finished_at = info.get("finished_at")
                started_at = info.get("started_at", 0)
                last_activity = finished_at if isinstance(finished_at, (int, float)) else started_at
                last_activity_float = _to_float(last_activity)
                if now - last_activity_float > self.STATUS_TTL_SECONDS:
                    expired.append(tid)

            for tid in expired:
                self._status.pop(tid, None)

            if len(self._status) > self.STATUS_MAX_ENTRIES:
                sorted_by_age = sorted(
                    self._status.items(),
                    key=lambda item: _to_float(item[1].get("started_at", 0)),
                )
                excess = len(self._status) - self.STATUS_MAX_ENTRIES
                for tid, _ in sorted_by_age[:excess]:
                    self._status.pop(tid, None)

            # Clean up finished tasks that may have leaked past done-callback
            finished_tasks = [
                tid for tid, task in self._tasks.items() if task.done()
            ]
            for tid in finished_tasks:
                self._tasks.pop(tid, None)

    async def has_task(self, task_id: str) -> bool:
        """Return True if an active task with the given ID exists."""
        async with self._lock:
            return task_id in self._tasks

    async def active_task_count(self) -> int:
        """Return the number of active (unfinished) tasks."""
        async with self._lock:
            return len(self._tasks)

    async def get_task(self, task_id: str) -> asyncio.Task[dict[str, object]] | None:
        """Return the active task for the given ID, or None."""
        async with self._lock:
            return self._tasks.get(task_id)


@dataclass
class AppState:
    """Application state container — pre-initialization, mutable for tests."""

    config: AppConfig
    llm: ILLM | None = None
    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    chunker: IChunker | None = None
    reranker: IReranker | None = None
    storage: IChatStorage | None = None
    rag_state: RAGState | None = None


@dataclass
class InitializedAppState:
    """Runtime application state — core adapters are guaranteed present."""

    config: AppConfig
    llm: ILLM
    embedder: IEmbedder
    vector_store: IVectorStore
    storage: IChatStorage
    chunker: IChunker
    reranker: IReranker
    rag_state: RAGState


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

    state.rag_state = RAGState()

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
    return InitializedAppState(
        config=cfg,
        llm=state.llm,
        embedder=state.embedder,
        vector_store=state.vector_store,
        storage=state.storage,
        chunker=state.chunker,
        reranker=state.reranker,
        rag_state=state.rag_state,
    )


def get_state(request: Request) -> InitializedAppState:
    """Get initialized app state. Raises RuntimeError if missing."""
    app_state = getattr(request.app.state, "app_state", None)
    if app_state is None:
        raise RuntimeError("State not initialized")
    return app_state
