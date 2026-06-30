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
    TokenizerConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.pipeline import ReindexStatusEntry
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.tokenizer import ITokenizer
from ai_assistant.core.task_registry import TaskRegistry

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
    "get_chunker_for_config",
    "get_state",
    "init_adapters",
]

_logger = get_logger("deps")


_MAX_STATUS_ENTRIES: int = 1000
_RUNNING_TTL_SECONDS: float = 28800.0  # 8h — reindex timeout is 4h

@dataclass
class RAGState:
    """Explicit per-instance RAG background task state.

    Replaces module-level globals to eliminate shared mutable state
    across tests and application instances.
    """

    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    _status: dict[str, ReindexStatusEntry] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def _cleanup_old_status(self) -> None:
        """Evict oldest completed/failed entries when limit exceeded.

        Also evict 'running' entries older than _RUNNING_TTL_SECONDS
        to prevent unbounded growth from orphaned tasks.
        """
        async with self._lock:
            now = time.time()
            stale_cutoff = now - _RUNNING_TTL_SECONDS

            # Always evict stale running entries regardless of total size
            stale_running = [
                tid
                for tid, entry in self._status.items()
                if entry.status == "running" and entry.started_at < stale_cutoff
            ]
            for tid in stale_running:
                del self._status[tid]

            if len(self._status) <= _MAX_STATUS_ENTRIES:
                return

            completed = [
                (tid, entry)
                for tid, entry in self._status.items()
                if entry.status in ("completed", "failed")
            ]
            completed.sort(key=lambda x: x[1].finished_at or 0.0)
            to_evict = len(self._status) - _MAX_STATUS_ENTRIES
            for tid, _ in completed[:to_evict]:
                del self._status[tid]

    async def start_task(self, task_id: str) -> None:
        """Atomically register a running task."""
        async with self._lock:
            self._status[task_id] = ReindexStatusEntry(
                status="running",
                started_at=time.time(),
            )

    async def complete_task(self, task_id: str, result: dict[str, object]) -> None:
        """Atomically mark task completed."""
        async with self._lock:
            old = self._status.get(task_id)
            started = old.started_at if old is not None else time.time()
            self._status[task_id] = ReindexStatusEntry(
                status="completed",
                started_at=started,
                finished_at=time.time(),
                result=result,
            )

    async def fail_task(self, task_id: str, error: str) -> None:
        """Atomically mark task failed."""
        async with self._lock:
            old = self._status.get(task_id)
            started = old.started_at if old is not None else time.time()
            self._status[task_id] = ReindexStatusEntry(
                status="failed",
                started_at=started,
                finished_at=time.time(),
                error=error,
            )

    async def get_status(self, task_id: str) -> dict[str, object] | None:
        """Return status as a JSON-compatible dict for the given task, or None."""
        async with self._lock:
            info = self._status.get(task_id)
            if info is None:
                return None
            d: dict[str, object] = {
                "status": info.status,
                "started_at": info.started_at,
            }
            if info.finished_at is not None:
                d["finished_at"] = info.finished_at
            if info.result is not None:
                d["result"] = info.result
            if info.error is not None:
                d["error"] = info.error
            return d


@dataclass
class AppState:
    """Application state container — pre-initialization, mutable for tests."""

    config: AppConfig
    task_registry: TaskRegistry | None = None
    llm: ILLM | None = None
    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    chunker: IChunker | None = None
    tokenizer: ITokenizer | None = None
    reranker: IReranker | None = None
    storage: IChatStorage | None = None
    rag_state: RAGState | None = None


@dataclass
class InitializedAppState:
    """Runtime application state — core adapters are guaranteed present."""

    config: AppConfig
    task_registry: TaskRegistry
    llm: ILLM
    embedder: IEmbedder
    vector_store: IVectorStore
    storage: IChatStorage
    chunker: IChunker
    tokenizer: ITokenizer
    reranker: IReranker
    rag_state: RAGState


# ---------------------------------------------------------------------------
# Config conversion — Pydantic -> dataclass for port contracts
# ---------------------------------------------------------------------------


def _tokenizer_data(cfg: AppConfig) -> TokenizerConfigData:
    c = cfg.tokenizer
    return TokenizerConfigData(
        provider=c.provider,
        local_dir=c.local_dir,
    )


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

    state.tokenizer = create_adapter("tokenizer", cfg.tokenizer.provider, _tokenizer_data(cfg))
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

    state.task_registry = TaskRegistry()
    state.rag_state = RAGState()

    if state.storage is None:
        raise RuntimeError("Storage adapter failed to initialize")
    return InitializedAppState(
        config=cfg,
        task_registry=state.task_registry,
        llm=state.llm,
        embedder=state.embedder,
        vector_store=state.vector_store,
        storage=state.storage,
        chunker=state.chunker,
        tokenizer=state.tokenizer,
        reranker=state.reranker,
        rag_state=state.rag_state,
    )


def get_state(request: Request) -> InitializedAppState:
    """Get initialized app state. Raises RuntimeError if missing."""
    app_state = getattr(request.app.state, "app_state", None)
    if app_state is None:
        raise RuntimeError("State not initialized")
    return app_state


def get_chunker_for_config(state: InitializedAppState, chunk_size: int | None = None) -> IChunker:
    """Return chunker, creating a new one if namespace requires different chunk_size.

    This factory lives in api.deps (not features/) because only api/ may
    import from adapters/. Features receive the chunker via AppState.
    """
    if chunk_size is None or chunk_size == state.config.chunker.chunk_size:
        return state.chunker
    cfg = state.config.chunker.model_copy(update={"chunk_size": chunk_size})
    return create_adapter(
        "chunker",
        cfg.provider,
        ChunkerConfigData(
            chunk_size=cfg.chunk_size,
            chunk_overlap=cfg.chunk_overlap,
        ),
    )
