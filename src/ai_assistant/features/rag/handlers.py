"""RAG feature HTTP handlers with namespace and reranker support."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.core.constants import DOCUMENTS_ROOT
from ai_assistant.core.logger import get_logger
from ai_assistant.features.rag.indexing import index_folder
from ai_assistant.features.rag.manager import IndexingManager, RAGManager
from ai_assistant.features.rag.schemas import (
    DeleteRequest,
    DeleteResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    NamespaceListResponse,
    QueryRequest,
    QueryResponse,
    SaveChatRequest,
)

__all__ = ["router"]

_logger = get_logger("rag.handlers")

router = APIRouter(prefix="/rag", tags=["rag"])

# ── Background reindex coordination ─────────────────────────────────────────
_reindex_semaphore = asyncio.Semaphore(1)
_reindex_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
_reindex_status: dict[str, dict[str, Any]] = {}
_reindex_lock = asyncio.Lock()

_REINDEX_STATUS_TTL_SECONDS = 3600
_REINDEX_STATUS_MAX_ENTRIES = 1000


async def _cleanup_reindex_status() -> None:
    """Remove expired entries and enforce max size cap on _reindex_status."""
    async with _reindex_lock:
        now = time.time()

        # TTL cleanup: remove entries whose last activity is older than TTL
        expired = [
            tid
            for tid, info in _reindex_status.items()
            if now - (info.get("finished_at") or info.get("started_at", 0))
            > _REINDEX_STATUS_TTL_SECONDS
        ]
        for tid in expired:
            _reindex_status.pop(tid, None)

        # Cap cleanup: if still over max, remove oldest by started_at
        if len(_reindex_status) > _REINDEX_STATUS_MAX_ENTRIES:
            sorted_by_age = sorted(
                _reindex_status.items(),
                key=lambda item: item[1].get("started_at", 0),
            )
            excess = len(_reindex_status) - _REINDEX_STATUS_MAX_ENTRIES
            for tid, _ in sorted_by_age[:excess]:
                _reindex_status.pop(tid, None)


def _get_rag_manager(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> RAGManager:
    return RAGManager(
        pipeline=state.pipeline,
        llm=state.llm,
        vector_store=state.vector_store,
        embedder=state.embedder,
        reranker=state.reranker,
    )


@router.post("/index", response_model=IndexResponse)
async def index_documents(
    req: IndexRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> IndexResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    ns_cfg = state.config.namespaces.get(namespace)

    # ── Per-namespace chunker override (only if size differs from base) ──
    chunker = state.chunker
    if ns_cfg is not None and ns_cfg.chunk_size != state.config.chunker.chunk_size:
        base_cfg = state.config.chunker
        ns_chunker_cfg = base_cfg.model_copy(update={"chunk_size": ns_cfg.chunk_size})
        chunker = create_adapter("chunker", base_cfg.provider, ns_chunker_cfg)

    manager = IndexingManager(
        chunker=chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )

    # ── Resource guard: document size ──
    max_doc_size = state.config.vector_store.max_document_size
    filtered_docs: list[dict[str, Any]] = []
    pre_errors: list[str] = []
    for doc in req.documents:
        content = doc.get("content", "")
        size = len(content.encode("utf-8"))
        if size > max_doc_size:
            doc_id = doc.get("id", "unknown")
            pre_errors.append(
                f"Document {doc_id} exceeds max size ({size} > {max_doc_size})"
            )
        else:
            filtered_docs.append(doc)

    if not filtered_docs:
        return IndexResponse(
            indexed_count=0,
            chunk_count=0,
            namespace=namespace,
            errors=pre_errors,
        )

    result = await manager.index_documents(filtered_docs, namespace=namespace)
    if pre_errors:
        result.setdefault("errors", []).extend(pre_errors)

    # Auto-save after indexing
    index_path = state.config.vector_store.index_path
    if index_path:
        try:
            await state.vector_store.save(index_path, namespace=namespace)
        except Exception:
            _logger.exception("Auto-save failed")
            result.setdefault("errors", []).append("Internal server error")
    return IndexResponse(**result, namespace=namespace)


@router.post("/query", response_model=QueryResponse)
async def query_rag(
    req: QueryRequest,
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> QueryResponse:
    cfg = state.config.rag
    ns = req.namespace or cfg.default_namespace
    ns_cfg = state.config.namespaces.get(ns)

    # Per-namespace overrides with global fallback
    prompt_name = req.prompt_name
    if prompt_name is None and ns_cfg is not None:
        prompt_name = ns_cfg.prompt
    if prompt_name is None:
        prompt_name = cfg.prompt_name or "rag_strict"

    relevance_threshold = cfg.relevance_threshold
    if ns_cfg is not None:
        relevance_threshold = ns_cfg.relevance_threshold

    result = await manager.query(
        query_text=req.query,
        top_k=req.top_k or cfg.top_k,
        prompt_name=prompt_name,
        prompt_version=req.prompt_version or cfg.prompt_version,
        namespace=ns,
        relevance_threshold=relevance_threshold,
    )
    return QueryResponse(**result)


@router.post("/delete", response_model=DeleteResponse)
async def delete_chunks(
    req: DeleteRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> DeleteResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    errors: list[str] = []
    deleted = 0
    try:
        if req.chunk_ids:
            await state.vector_store.delete(req.chunk_ids, namespace=namespace)
            deleted += len(req.chunk_ids)
        elif req.document_ids:
            all_chunks = await state.vector_store.list_by_filter(
                {}, namespace=namespace
            )
            to_delete = []
            for chunk_id, meta in all_chunks:
                if meta.get("source") in req.document_ids:
                    to_delete.append(chunk_id)
            if to_delete:
                await state.vector_store.delete(to_delete, namespace=namespace)
                deleted += len(to_delete)
    except Exception:
        _logger.exception("Delete chunks failed")
        errors.append("Internal server error")
    return DeleteResponse(deleted_chunks=deleted, errors=errors)


@router.get("/health", response_model=HealthResponse)
async def rag_health(
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> HealthResponse:
    health = await manager.health()
    return HealthResponse(
        status=health["status"],
        index_loaded=health["index_loaded"],
        chunk_count=health["chunk_count"],
        embedder_dim=state.embedder.dimension,
    )


@router.get("/namespaces", response_model=NamespaceListResponse)
async def list_namespaces(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> NamespaceListResponse:
    index_path = state.config.vector_store.index_path
    namespaces: list[str] = []
    if index_path:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
        except Exception:
            _logger.exception("List namespaces failed")
    if not namespaces:
        namespaces = ["default"]
    return NamespaceListResponse(namespaces=namespaces)


@router.post("/save-chat", response_model=None)
async def save_chat(
    req: SaveChatRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    namespace = req.namespace
    filename = req.filename
    content = req.content

    # Save to documents folder
    folder = DOCUMENTS_ROOT / namespace
    folder_resolved = await asyncio.to_thread(folder.resolve)
    docs_resolved = await asyncio.to_thread(DOCUMENTS_ROOT.resolve)

    if not folder_resolved.is_relative_to(docs_resolved):
        raise HTTPException(status_code=400, detail="Invalid namespace")

    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    file_path = (folder / filename).resolve()
    if not file_path.is_relative_to(folder_resolved):
        raise HTTPException(status_code=400, detail="Path traversal detected")

    try:
        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")
    except Exception:
        _logger.exception("Failed to save file")
        raise HTTPException(status_code=500, detail="Internal server error") from None

    # Index the saved chat
    try:
        manager = IndexingManager(
            chunker=state.chunker,
            embedder=state.embedder,
            vector_store=state.vector_store,
        )
        result = await manager.index_documents(
            [
                {
                    "id": file_path.stem,
                    "content": content,
                    "metadata": {
                        "source": str(file_path),
                        "folder": namespace,
                        "type": "chat_export",
                    },
                }
            ],
            namespace=namespace,
        )

        # Auto-save index
        index_path = state.config.vector_store.index_path
        if index_path:
            await state.vector_store.save(index_path, namespace=namespace)

        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "indexed_count": result.get("indexed_count", 0),
            "chunk_count": result.get("chunk_count", 0),
        }
    except Exception as e:
        # File saved but indexing failed
        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "indexed": False,
            "error": str(e),
        }


@router.post("/reindex", response_model=None)
async def reindex_documents(
    req: dict[str, Any],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    """Reindex documents from folders. Returns immediately, runs in background."""
    folder = req.get("folder")
    clear = req.get("clear", False)

    task_id = str(uuid.uuid4())

    async def _run() -> dict[str, Any]:
        async with _reindex_semaphore:
            await _cleanup_reindex_status()
            async with _reindex_lock:
                _reindex_status[task_id] = {
                    "status": "running",
                    "started_at": time.time(),
                }
            try:
                result = await index_folder(
                    folder=folder,
                    clear=clear,
                    chunker=state.chunker,
                    embedder=state.embedder,
                    vector_store=state.vector_store,
                    max_file_size=state.config.vector_store.max_document_size,
                )
                async with _reindex_lock:
                    _reindex_status[task_id] = {
                        "status": "completed",
                        "result": result,
                        "finished_at": time.time(),
                    }
                return result
            except Exception:
                _logger.exception("Background reindex failed")
                async with _reindex_lock:
                    _reindex_status[task_id] = {
                        "status": "failed",
                        "error": "Internal server error",
                        "finished_at": time.time(),
                    }
                raise
            finally:
                _reindex_tasks.pop(task_id, None)

    task = asyncio.create_task(_run())
    _reindex_tasks[task_id] = task
    return {"status": "started", "task_id": task_id}


@router.get("/reindex/status/{task_id}", response_model=None)
async def reindex_status(task_id: str) -> dict[str, Any]:
    """Get status of a background reindex task."""
    await _cleanup_reindex_status()
    async with _reindex_lock:
        if task_id in _reindex_status:
            info = _reindex_status[task_id]
            return {"task_id": task_id, **info}
    return {"task_id": task_id, "status": "unknown"}
