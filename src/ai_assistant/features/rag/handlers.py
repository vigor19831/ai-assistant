
"""RAG feature HTTP handlers with namespace and reranker support."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ai_assistant.api.deps import (
    InitializedAppState,
    get_chunker_for_config,
    get_state,
)
from ai_assistant.core.config import _get_chat_namespace
from ai_assistant.core.domain.errors import LLM_UNAVAILABLE
from ai_assistant.core.logger import get_logger
from ai_assistant.core.query_parser import parse_rag_query
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
    ReindexRequest,
    SaveChatRequest,
)

__all__ = ["router"]

_logger = get_logger("rag.handlers")

router = APIRouter(prefix="/rag", tags=["rag"])


def _get_rag_manager(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> RAGManager:
    return RAGManager(
        llm=state.llm,
        vector_store=state.vector_store,
        embedder=state.embedder,
        reranker=state.reranker,
        token_margin_min=state.config.rag.token_margin_min,
        token_margin_pct=state.config.rag.token_margin_pct,
        tokenizer=state.tokenizer,
    )


@router.post("/index", response_model=IndexResponse)
async def index_documents(
    req: IndexRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> IndexResponse:
    trace_id = uuid.uuid4().hex
    start = time.perf_counter()
    namespace = req.namespace or state.config.rag.default_namespace
    ns_cfg = state.config.namespaces.get(namespace)

    # -- Per-namespace chunker override (only if size differs from base) --
    chunker = get_chunker_for_config(state, ns_cfg.chunk_size if ns_cfg else None)

    manager = IndexingManager(
        chunker=chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )

    # -- Resource guard: document size --
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
        _logger.info(
            "Index documents: all filtered by size",
            extra={"trace_id": trace_id, "namespace": namespace},
        )
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
            _logger.exception(
                "Auto-save failed",
                extra={"trace_id": trace_id, "namespace": namespace},
            )
            result.setdefault("errors", []).append("Internal server error")

    duration_ms = int((time.perf_counter() - start) * 1000)
    _logger.info(
        "Index documents completed",
        extra={
            "trace_id": trace_id,
            "namespace": namespace,
            "indexed_count": result.get("indexed_count", 0),
            "chunk_count": result.get("chunk_count", 0),
            "duration_ms": duration_ms,
            "errors": len(result.get("errors", [])),
        },
    )
    return IndexResponse(**result, namespace=namespace)


@router.post("/query", response_model=QueryResponse)
async def query_rag(
    req: QueryRequest,
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> QueryResponse:
    trace_id = uuid.uuid4().hex
    start = time.perf_counter()
    cfg = state.config.rag
    ns = req.namespace or cfg.default_namespace
    query_text = req.query

    # Fallback: if namespace not explicitly set, try parsing from query text
    if ns == cfg.default_namespace:
        parsed_text, parsed_ns = parse_rag_query(req.query)
        if parsed_ns != "default":
            query_text = parsed_text
            ns = parsed_ns

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

    _logger.info(
        "RAG query start",
        extra={"trace_id": trace_id, "namespace": ns, "query_len": len(query_text)},
    )

    result = await manager.query(
        query_text=query_text,
        top_k=req.top_k or cfg.top_k,
        prompt_name=prompt_name,
        prompt_version=req.prompt_version or cfg.prompt_version,
        namespace=ns,
        relevance_threshold=relevance_threshold,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    _logger.info(
        "RAG query completed",
        extra={
            "trace_id": trace_id,
            "namespace": ns,
            "query_len": len(query_text),
            "chunks_used": result.get("chunks_used", 0),
            "duration_ms": duration_ms,
            "errors": len(result.get("errors", [])),
        },
    )
    for err in result.get("errors", []):
        if err.startswith(LLM_UNAVAILABLE):
            _logger.warning(
                "RAG query: LLM unavailable",
                extra={"trace_id": trace_id, "error": err},
            )
            raise HTTPException(
                status_code=503,
                detail="LLM service temporarily unavailable. Please try again later.",
            )
    return QueryResponse(**result)


@router.post("/delete", response_model=DeleteResponse)
async def delete_chunks(
    req: DeleteRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> DeleteResponse:
    trace_id = uuid.uuid4().hex
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
        _logger.info(
            "Delete chunks completed",
            extra={
                "trace_id": trace_id,
                "namespace": namespace,
                "deleted": deleted,
            },
        )
    except Exception:
        _logger.exception(
            "Delete chunks failed",
            extra={"trace_id": trace_id, "namespace": namespace},
        )
        errors.append("Internal server error")
    return DeleteResponse(deleted_chunks=deleted, errors=errors)


@router.get("/health", response_model=HealthResponse)
async def rag_health(
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> HealthResponse:
    trace_id = uuid.uuid4().hex
    health = await manager.health()
    _logger.info(
        "RAG health check",
        extra={"trace_id": trace_id, "status": health["status"]},
    )
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
    trace_id = uuid.uuid4().hex
    index_path = state.config.vector_store.index_path
    namespaces: list[str] = []
    if index_path:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
        except Exception:
            _logger.exception(
                "List namespaces failed",
                extra={"trace_id": trace_id},
            )
    if not namespaces:
        namespaces = ["default"]
    _logger.info(
        "List namespaces",
        extra={"trace_id": trace_id, "count": len(namespaces)},
    )
    return NamespaceListResponse(namespaces=namespaces)


@router.post("/save-chat", response_model=None)
async def save_chat(
    req: SaveChatRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex
    namespace = req.namespace
    if not re.match(r"^[a-z]+$", namespace):
        _logger.warning(
            "Invalid namespace in save-chat",
            extra={"trace_id": trace_id, "namespace": namespace},
        )
        raise HTTPException(
            status_code=400, detail="Invalid namespace: must be lowercase letters only"
        )
    filename = req.filename
    content = req.content

    # Save to chat exports folder
    exports_root = Path(state.config.rag.chat_exports_root)
    folder = exports_root / namespace
    folder_resolved = await asyncio.to_thread(folder.resolve)
    exports_root_resolved = await asyncio.to_thread(exports_root.resolve)

    if not folder_resolved.is_relative_to(exports_root_resolved):
        _logger.warning(
            "Invalid namespace path in save-chat",
            extra={"trace_id": trace_id, "namespace": namespace},
        )
        raise HTTPException(status_code=400, detail="Invalid namespace")

    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    file_path = (folder / filename).resolve()
    if not file_path.is_relative_to(folder_resolved):
        _logger.warning(
            "Path traversal detected in save-chat",
            extra={"trace_id": trace_id, "filename": filename},
        )
        raise HTTPException(status_code=400, detail="Path traversal detected")

    try:
        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")
    except Exception:
        _logger.exception(
            "Failed to save file",
            extra={"trace_id": trace_id, "path": str(file_path)},
        )
        raise HTTPException(status_code=500, detail="Internal server error") from None

    # Index the saved chat only if explicitly enabled
    if not state.config.rag.index_chat_exports:
        _logger.info(
            "Chat saved, indexing skipped",
            extra={"trace_id": trace_id, "path": str(file_path)},
        )
        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "indexed": False,
            "reason": "index_chat_exports is disabled",
        }

    # Collision detection: verify no user namespace uses reserved prefix
    existing_namespaces = await state.vector_store.list_namespaces(
        state.config.vector_store.index_path
    )
    chat_namespace = _get_chat_namespace(namespace)
    if chat_namespace in existing_namespaces:
        # Check if it's actually a user-created namespace (not our chat export)
        # by looking for any non-chat_export type chunks
        non_chat_chunks = await state.vector_store.list_by_filter(
            {"type": "document"}, namespace=chat_namespace
        )
        if non_chat_chunks:
            _logger.warning(
                "Namespace collision detected",
                extra={
                    "trace_id": trace_id,
                    "base_namespace": namespace,
                    "chat_namespace": chat_namespace,
                },
            )
            return {
                "saved": True,
                "path": str(file_path),
                "namespace": namespace,
                "indexed": False,
                "error": "Namespace collision: '" + chat_namespace + "' already exists with documents",
            }
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
                        "source": str(Path(namespace) / filename),
                        "folder": namespace,
                        "type": "chat_export",
                    },
                }
            ],
            namespace=chat_namespace,
        )

        # Auto-save index
        index_path = state.config.vector_store.index_path
        if index_path:
            await state.vector_store.save(index_path, namespace=chat_namespace)

        _logger.info(
            "Chat saved and indexed",
            extra={
                "trace_id": trace_id,
                "path": str(file_path),
                "chat_namespace": chat_namespace,
                "indexed_count": result.get("indexed_count", 0),
                "chunk_count": result.get("chunk_count", 0),
            },
        )
        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "chat_namespace": chat_namespace,
            "indexed_count": result.get("indexed_count", 0),
            "chunk_count": result.get("chunk_count", 0),
        }
    except Exception as e:
        _logger.exception(
            "Chat saved but indexing failed",
            extra={"trace_id": trace_id, "error": str(e)},
        )
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
    req: ReindexRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    """Reindex documents from folders. Returns immediately, runs in background."""
    trace_id = uuid.uuid4().hex
    folder = req.folder
    clear = req.clear
    task_id = str(uuid.uuid4())
    rag_state = state.rag_state

    _logger.info(
        "Reindex started",
        extra={
            "trace_id": trace_id,
            "task_id": task_id,
            "folder": folder,
            "clear": clear,
        },
    )

    async def _run() -> dict[str, Any]:
        async with rag_state.semaphore:
            await rag_state.cleanup_status()
            await rag_state.start_task(task_id)
            try:
                # If clearing, also clear associated chat namespaces
                if clear and folder is not None:
                    chat_ns = _get_chat_namespace(folder)
                    try:
                        all_chat_chunks = await state.vector_store.list_by_filter(
                            {}, namespace=chat_ns
                        )
                        if all_chat_chunks:
                            await state.vector_store.delete(
                                [cid for cid, _ in all_chat_chunks], namespace=chat_ns
                            )
                            _logger.info(
                                "Cleared chat namespace during reindex",
                                extra={
                                    "trace_id": trace_id,
                                    "namespace": folder,
                                    "chat_namespace": chat_ns,
                                },
                            )
                    except Exception:
                        _logger.warning(
                            "Failed to clear chat namespace during reindex",
                            extra={
                                "trace_id": trace_id,
                                "namespace": folder,
                                "chat_namespace": chat_ns,
                            },
                        )

                result = await index_folder(
                    folder=folder,
                    clear=clear,
                    chunker=state.chunker,
                    embedder=state.embedder,
                    vector_store=state.vector_store,
                    max_file_size=state.config.vector_store.max_document_size,
                    documents_root=Path(state.config.rag.documents_root),
                )
                await rag_state.complete_task(task_id, result)
                _logger.info(
                    "Reindex completed",
                    extra={"trace_id": trace_id, "task_id": task_id},
                )
                return result
            except Exception:
                _logger.exception(
                    "Background reindex failed",
                    extra={"trace_id": trace_id, "task_id": task_id},
                )
                await rag_state.fail_task(task_id, "Internal server error")
                raise

    task = asyncio.create_task(_run())
    await rag_state.register_task(task_id, task)
    return {"status": "started", "task_id": task_id}


@router.get("/reindex/status/{task_id}", response_model=None)
async def reindex_status(
    task_id: str,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    """Get status of a background reindex task."""
    trace_id = uuid.uuid4().hex
    rag_state = state.rag_state
    await rag_state.cleanup_status()
    info = await rag_state.get_status(task_id)
    _logger.info(
        "Reindex status checked",
        extra={"trace_id": trace_id, "task_id": task_id, "status": info.get("status") if info else "unknown"},
    )
    if info is not None:
        return {"task_id": task_id, **info}
    return {"task_id": task_id, "status": "unknown"}
