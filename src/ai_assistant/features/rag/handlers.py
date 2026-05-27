"""RAG feature HTTP handlers with namespace and reranker support."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ai_assistant.api.deps import AppState, get_state
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

DOCUMENTS_ROOT = Path("documents")

# ── Background reindex coordination ─────────────────────────────────────────
_reindex_semaphore = asyncio.Semaphore(1)
_reindex_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
_reindex_status: dict[str, dict[str, Any]] = {}


def _get_indexing_manager(
    state: Annotated[AppState, Depends(get_state)],
) -> IndexingManager:
    return IndexingManager(
        chunker=state.chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )


def _get_rag_manager(state: Annotated[AppState, Depends(get_state)]) -> RAGManager:
    if state.pipeline is None:
        raise HTTPException(status_code=500, detail="RAG pipeline not initialized")
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
    manager: Annotated[IndexingManager, Depends(_get_indexing_manager)],
    state: Annotated[AppState, Depends(get_state)],
) -> IndexResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    result = await manager.index_documents(req.documents, namespace=namespace)
    # Auto-save after indexing
    index_path = getattr(state.config.vector_store, "index_path", None)
    if index_path:
        try:
            await state.vector_store.save(index_path, namespace=namespace)
        except Exception:
            _logger.exception("Auto-save failed")
            result["errors"].append("Internal server error")
    return IndexResponse(**result, namespace=namespace)


@router.post("/query", response_model=QueryResponse)
async def query_rag(
    req: QueryRequest,
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[AppState, Depends(get_state)],
) -> QueryResponse:
    cfg = state.config.rag
    # Use strict prompt by default
    prompt_name = req.prompt_name or cfg.prompt_name or "rag_strict"

    # Get relevance threshold from config or request
    relevance_threshold = getattr(cfg, "relevance_threshold", 0.3)

    result = await manager.query(
        query_text=req.query,
        top_k=req.top_k or cfg.top_k,
        prompt_name=prompt_name,
        prompt_version=req.prompt_version or cfg.prompt_version,
        namespace=req.namespace or cfg.default_namespace,
        relevance_threshold=relevance_threshold,
    )
    return QueryResponse(**result)


@router.post("/delete", response_model=DeleteResponse)
async def delete_chunks(
    req: DeleteRequest,
    state: Annotated[AppState, Depends(get_state)],
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
    state: Annotated[AppState, Depends(get_state)],
) -> HealthResponse:
    health = await manager.health()
    return HealthResponse(
        status=health["status"],
        index_loaded=health["index_loaded"],
        chunk_count=health["chunk_count"],
        embedder_dim=getattr(state.embedder, "dimension", None),
    )


@router.get("/namespaces", response_model=NamespaceListResponse)
async def list_namespaces(
    state: Annotated[AppState, Depends(get_state)],
) -> NamespaceListResponse:
    index_path = getattr(state.config.vector_store, "index_path", None)
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
    state: Annotated[AppState, Depends(get_state)],
) -> dict[str, Any]:
    namespace = req.namespace
    filename = req.filename
    content = req.content

    # Save to documents folder
    folder = DOCUMENTS_ROOT / namespace
    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    folder_resolved = await asyncio.to_thread(folder.resolve)

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
        index_path = getattr(state.config.vector_store, "index_path", None)
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
    state: Annotated[AppState, Depends(get_state)],
) -> dict[str, Any]:
    """Reindex documents from folders. Returns immediately, runs in background."""
    folder = req.get("folder")
    clear = req.get("clear", False)

    task_id = str(uuid.uuid4())

    async def _run() -> dict[str, Any]:
        async with _reindex_semaphore:
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
                )
                _reindex_status[task_id] = {
                    "status": "completed",
                    "result": result,
                    "finished_at": time.time(),
                }
                return result
            except Exception:
                _logger.exception("Background reindex failed")
                _reindex_status[task_id] = {
                    "status": "failed",
                    "error": "Internal server error",
                    "finished_at": time.time(),
                }
                raise

    task = asyncio.create_task(_run())
    _reindex_tasks[task_id] = task
    return {"status": "started", "task_id": task_id}


@router.get("/reindex/status/{task_id}", response_model=None)
async def reindex_status(task_id: str) -> dict[str, Any]:
    """Get status of a background reindex task."""
    if task_id in _reindex_status:
        info = _reindex_status[task_id]
        return {"task_id": task_id, **info}
    return {"task_id": task_id, "status": "unknown"}
