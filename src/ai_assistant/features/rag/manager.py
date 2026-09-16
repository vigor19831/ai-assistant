"""RAG manager — uses pipeline per namespace."""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from ai_assistant.api.deps import InitializedAppState
from ai_assistant.core.config import RAGStep, SourceConfig
from ai_assistant.core.constants import (
    DEFAULT_RAG_PROMPT,
    SOURCE_INDEX_TIMEOUT,
    is_refusal_answer,
)
from ai_assistant.core.domain.configs import SamplingConfig
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.errors import (
    LLM_UNAVAILABLE_MSG,
    ConfigurationError,
)
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.core.ports import (
    ILLM,
    IChunker,
    IEmbedder,
    IReranker,
    ITokenizer,
    IVectorStore,
)
from ai_assistant.core.ports.lexical_index import ILexicalIndex

_logger = get_logger("rag.manager")

# --- SourceWatcher timeouts (seconds) ---
_WATCHER_POLL_INTERVAL = 60.0
_WATCHER_STOP_TIMEOUT = 10.0
_WATCHER_TASK_STOP_TIMEOUT = 60.0
# --- SourceWatcher retry policy ---
# Consecutive failed reindex attempts before the watcher gives up and
# waits for file changes or a manual POST /rag/reindex.
_WATCHER_MAX_ATTEMPTS = 3


class IndexingManager:
    """Handles document ingestion: chunk + embed + store per namespace.

    With a lexical_index the write is dual-store: vector first (the
    capacity gatekeeper), lexical mirrored after (hybrid 4a).
    """

    def __init__(
        self,
        chunker: IChunker,
        embedder: IEmbedder,
        vector_store: IVectorStore,
        lexical_index: ILexicalIndex | None = None,
    ) -> None:
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.lexical_index = lexical_index

    async def index_documents(
        self,
        documents: list[dict[str, Any]],
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Chunk, embed and upsert documents in namespace."""
        start = time.perf_counter()
        all_chunks: list[Chunk] = []
        errors: list[str] = []
        successful_docs = 0

        for doc in documents:
            doc_id = doc.get("id")
            if not doc_id:
                errors.append("Document missing 'id' field, skipped")
                continue

            try:
                document = Document(
                    id=doc_id,
                    content=doc.get("content", ""),
                    metadata=doc.get("metadata", {}),
                )
                doc_source_uri = document.metadata.get("source_uri")
                chunks = await self.chunker.chunk(document)
                for idx, chunk in enumerate(chunks):
                    chunk_source_uri = (
                        chunk.metadata.source_uri
                        if chunk.metadata and chunk.metadata.source_uri
                        else doc_source_uri
                    )
                    all_chunks.append(
                        replace(
                            chunk,
                            metadata=ChunkMetadata(
                                source=document.id,
                                index=idx,
                                total_chunks=len(chunks),
                                original_path=chunk.metadata.original_path
                                if chunk.metadata
                                else document.metadata.get("original_path"),
                                source_uri=chunk_source_uri,
                                last_modified=chunk.metadata.last_modified
                                if chunk.metadata and chunk.metadata.last_modified
                                else document.metadata.get("last_modified"),
                                custom=chunk.metadata.custom if chunk.metadata else {},
                            ),
                        )
                    )
                successful_docs += 1
            except Exception:
                _logger.exception(
                    "Failed to chunk document",
                    extra={"doc_id": doc_id, "namespace": namespace},
                )
                errors.append(f"Failed to chunk document {doc_id}")

        if not all_chunks:
            return {
                "indexed_count": 0,
                "chunk_count": 0,
                "errors": errors or ["No chunks produced from documents"],
                "indexed_uris": {},
            }

        texts = [c.text for c in all_chunks]
        # Retry lives in the adapter: OpenAICompatibleEmbedder retries each
        # batch inside _post_embeddings (@with_retry). Failures beyond that
        # are retried by the watcher's bounded attempts (drift #42).
        embeddings = await self.embedder.embed(texts)

        for i, emb in enumerate(embeddings):
            all_chunks[i] = replace(all_chunks[i], embedding=emb)

        # Write order (hybrid 4a): vector store first — the capacity
        # gatekeeper (max_chunks, drift #48/#107); a refusal stops the
        # run before the lexical leg ever runs. A lexical failure is
        # recorded, not raised: the run reports success=False (drift
        # #113), the watcher retries, and the dual-store skip guard
        # re-reads the document (the lexical side lacks evidence).
        # Invariant: lexical contains a uri => vector contains it.
        await self.vector_store.upsert(all_chunks, namespace=namespace)
        if self.lexical_index is not None:
            try:
                await self.lexical_index.upsert(all_chunks, namespace=namespace)
            except Exception:
                _logger.exception(
                    "Lexical index write failed",
                    extra={"namespace": namespace},
                )
                errors.append(f"Lexical index write failed for {namespace}")

        indexed_uris: dict[str, list[str]] = {}
        for chunk in all_chunks:
            if chunk.metadata and chunk.metadata.source_uri:
                indexed_uris.setdefault(chunk.metadata.source_uri, []).append(chunk.id)

        duration_ms = int((time.perf_counter() - start) * 1000)
        _logger.info(
            "Documents indexed",
            extra={
                "namespace": namespace,
                "indexed_count": successful_docs,
                "chunk_count": len(all_chunks),
                "duration_ms": duration_ms,
            },
        )
        return {
            "indexed_count": successful_docs,
            "chunk_count": len(all_chunks),
            "errors": errors,
            "indexed_uris": indexed_uris,
        }


class RAGManager:
    """Handles RAG queries using the pipeline per namespace."""

    def __init__(
        self,
        llm: ILLM,
        vector_store: IVectorStore,
        embedder: IEmbedder,
        reranker: IReranker,
        lexical_index: ILexicalIndex | None = None,
        token_margin_min: int = 256,
        token_margin_pct: float = 0.1,
        tokenizer: ITokenizer | None = None,
        rag_steps: list[RAGStep] | None = None,
        system_message: str | None = None,
        sampling: SamplingConfig | None = None,
    ) -> None:
        # Build pipeline from config step names, validating each against STEP_REGISTRY.
        # Default: full RAG pipeline with all steps.
        step_names = (
            rag_steps
            if rag_steps is not None
            else [
                RAGStep.EMBED_QUERY,
                RAGStep.RETRIEVE,
                RAGStep.RERANK,
                RAGStep.BUILD_CONTEXT,
                RAGStep.GENERATE,
            ]
        )
        step_funcs = []
        for name in step_names:
            func = STEP_REGISTRY.get(name)
            if func is None:
                raise ConfigurationError(
                    f"Unknown pipeline step: {name!r}. "
                    f"Available: {list(STEP_REGISTRY.keys())}"
                )
            step_funcs.append(func)
        self.pipeline = RAGPipeline(step_funcs)
        self.llm = llm
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker
        self.lexical_index = lexical_index
        self.token_margin_min = token_margin_min
        self.token_margin_pct = token_margin_pct
        self.tokenizer = tokenizer
        self.system_message = system_message
        self.sampling = sampling

    async def query(
        self,
        query_text: str,
        top_k: int = 5,
        prompt_name: str = DEFAULT_RAG_PROMPT,
        prompt_version: str = "v1",
        namespace: str = "default",
        trace_id: str = "",
        chat_history: tuple[tuple[str, str], ...] = (),
    ) -> dict[str, Any]:
        """Run RAG pipeline for query."""
        start = time.perf_counter()
        from ai_assistant.core.domain.pipeline import PipelineConfig

        pipeline_config = PipelineConfig(
            top_k=top_k,
            namespace=namespace,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            token_margin_min=self.token_margin_min,
            token_margin_pct=self.token_margin_pct,
            system_message=self.system_message,
            sampling=self.sampling or SamplingConfig(),
        )
        data = PipelineData(
            query=UserMessage(text=query_text),
            original_query=UserMessage(text=query_text),
            chat_history=chat_history,
            trace_id=trace_id or uuid.uuid4().hex,
            llm=self.llm,
            embedder=self.embedder,
            vector_store=self.vector_store,
            reranker=self.reranker,
            lexical_index=self.lexical_index,
            pipeline_config=pipeline_config,
            tokenizer=self.tokenizer,
        )
        result = await self.pipeline.run(data)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if result.errors:
            _logger.warning(
                "RAG pipeline completed with errors",
                extra={
                    "namespace": namespace,
                    "errors": list(result.errors),
                    "trace_id": data.trace_id,
                },
            )
        _logger.info(
            "RAG pipeline completed",
            extra={
                "namespace": namespace,
                "chunks_used": len(result.chunks),
                "duration_ms": duration_ms,
                "errors": len(result.errors),
            },
        )
        context_tokens = 0
        if self.tokenizer is not None and result.context:
            context_tokens = await asyncio.to_thread(
                self.tokenizer.count, result.context
            )

        metrics = {
            "chunks_used": len(result.chunks),
            "rerank_scores": list(result.rerank_scores) if result.rerank_scores else [],
            "context_tokens": context_tokens,
            "prompt_name": prompt_name,
            "pipeline_errors": list(result.errors),
            "duration_ms": duration_ms,
        }

        # Strict RAG contract (drift #50): a refusal is a complete
        # answer with no evidence. Retrieved chunks the model refused
        # to use are not sources — returning them would contradict the
        # answer text. One shared refusal check for both entry paths
        # (drift #122): preamble refusals count too — exact-match-only
        # let them carry sources via /rag/query.
        answer_text = result.response.text if result.response else ""
        is_refusal = is_refusal_answer(answer_text)
        # An LLM-unavailable answer is an error, not a refusal — but it
        # carries no evidence either (drift #50 shape); the handler
        # converts it into a 503 (drift #122).
        is_unavailable = answer_text.strip() == LLM_UNAVAILABLE_MSG
        if is_refusal or is_unavailable:
            return {
                "answer": answer_text,
                "sources": [],
                "chunks_used": 0,
                "errors": list(result.errors),
                "metrics": metrics,
            }
        return {
            "answer": answer_text,
            "sources": [
                {
                    "id": c.id,
                    "text": c.text,
                    "metadata": c.metadata,
                }
                for c in result.chunks
            ],
            "chunks_used": len(result.chunks),
            "errors": list(result.errors),
            "metrics": metrics,
        }

    async def health(self) -> dict[str, Any]:
        """Return RAG health status."""
        index_path = self.vector_store.index_path
        index_loaded = False
        chunk_count = 0
        try:
            namespaces = await self.vector_store.list_namespaces(index_path)
            index_loaded = len(namespaces) > 0
            for ns in namespaces:
                chunks = await asyncio.wait_for(
                    self.vector_store.list_by_filter({}, namespace=ns),
                    timeout=5.0,
                )
                chunk_count += len(chunks)
        except TimeoutError:
            _logger.warning("Health check timed out", extra={"index_path": index_path})
        except Exception:
            _logger.exception("Health check failed")
        return {
            "status": "ok" if index_loaded else "empty",
            "index_loaded": index_loaded,
            "chunk_count": chunk_count,
        }


class SourceWatcher:
    """Polls source directories and triggers reindex on filesystem changes."""

    def __init__(
        self,
        sources: list[SourceConfig],
        state: InitializedAppState,
        index_fn: Callable[[SourceConfig], Awaitable[None]],
        interval: float = _WATCHER_POLL_INTERVAL,
    ) -> None:
        self._sources = sources
        self._state = state
        self._index_fn = index_fn
        self._interval = interval
        self._snapshots: dict[str, dict[str, tuple[float, int]]] = {}
        self._failures: dict[str, int] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._index_tasks: dict[str, asyncio.Task[None]] = {}

    @staticmethod
    def _scan(path: Path, patterns: list[str]) -> dict[str, tuple[float, int]]:
        """Return {abspath: (mtime, size)} for files matching *patterns*.

        Only matched files: a change in an ignored neighbor (e.g. a
        .zip dropped into documents/) must not trigger a reindex pass.
        """
        snapshot: dict[str, tuple[float, int]] = {}
        for root, _, files in os.walk(path):
            for name in files:
                if not any(fnmatch.fnmatch(name, pat) for pat in patterns):
                    continue
                fp = Path(root) / name
                try:
                    st = fp.stat()
                    snapshot[str(fp)] = (st.st_mtime, st.st_size)
                except OSError:
                    pass
        return snapshot

    async def _check_once(self) -> None:
        for src in self._sources:
            path = Path(src.path)
            if not await asyncio.to_thread(path.exists):
                continue
            key = str(path)
            task = self._index_tasks.get(key)
            if task is not None and not task.done():
                _logger.debug("Skipping reindex, still running", extra={"source": key})
                continue
            current = await asyncio.to_thread(self._scan, path, src.include)
            previous = self._snapshots.get(key, {})
            if current != previous:
                _logger.info("Source changed, reindexing", extra={"source": src.path})
                self._index_tasks[key] = asyncio.create_task(
                    self._run_index(src, key, current)
                )

    async def _run_index(
        self,
        src: SourceConfig,
        snapshot_key: str,
        snapshot: dict[str, tuple[float, int]],
    ) -> None:
        try:
            await asyncio.wait_for(self._index_fn(src), timeout=SOURCE_INDEX_TIMEOUT)
        except TimeoutError:
            _logger.error("Auto-reindex timed out", extra={"source": src.path})
            self._register_failure(src, snapshot_key, snapshot)
            return
        except Exception:
            _logger.exception("Auto-reindex failed", extra={"source": src.path})
            self._register_failure(src, snapshot_key, snapshot)
            return
        # Success: consume the change and reset the failure counter.
        self._failures.pop(snapshot_key, None)
        self._snapshots[snapshot_key] = snapshot

    def _register_failure(
        self,
        src: SourceConfig,
        snapshot_key: str,
        snapshot: dict[str, tuple[float, int]],
    ) -> None:
        """Bounded retry: N attempts per change, then give up.

        The snapshot is NOT updated on failure, so the next poll
        re-detects the change and retries. After N consecutive failures
        the snapshot is consumed and an error is logged; new file
        changes or a manual POST /rag/reindex start a fresh cycle.
        """
        attempts = self._failures.get(snapshot_key, 0) + 1
        if attempts < _WATCHER_MAX_ATTEMPTS:
            self._failures[snapshot_key] = attempts
            _logger.warning(
                "Auto-reindex failed, will retry on next poll",
                extra={
                    "source": src.path,
                    "attempt": attempts,
                    "max_attempts": _WATCHER_MAX_ATTEMPTS,
                },
            )
            return
        self._failures.pop(snapshot_key, None)
        self._snapshots[snapshot_key] = snapshot
        _logger.error(
            f"Auto-reindex failed {_WATCHER_MAX_ATTEMPTS} times, giving up "
            "until files change. Run POST /rag/reindex to retry manually.",
            extra={"source": src.path, "attempts": _WATCHER_MAX_ATTEMPTS},
        )

    async def _loop(self) -> None:
        while not self._stop.is_set():
            await self._check_once()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)

    def start(self) -> None:
        """Start the watcher loop. Idempotent."""
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Unconditional shutdown. Who starts the loop — stops it."""
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=_WATCHER_STOP_TIMEOUT)
            except TimeoutError:
                _logger.warning("Watchdog loop shutdown timed out")
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            self._task = None
        for key, task in list(self._index_tasks.items()):
            if not task.done():
                try:
                    await asyncio.wait_for(task, timeout=_WATCHER_TASK_STOP_TIMEOUT)
                except TimeoutError:
                    _logger.warning(
                        "Index task shutdown timed out",
                        extra={"source": key},
                    )
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            self._index_tasks.pop(key, None)
