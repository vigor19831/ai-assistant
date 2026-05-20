"""RAG feature HTTP handlers with namespace and reranker support."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import AppState, get_state
from api.security import require_api_key
from features.rag.manager import IndexingManager, RAGManager
from features.rag.schemas import (
    DeleteRequest,
    DeleteResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    NamespaceListResponse,
    QueryRequest,
    QueryResponse,
)

router = APIRouter(prefix="/rag", tags=["rag"])

DOCUMENTS_ROOT = Path("documents")


def _get_indexing_manager(state: AppState = Depends(get_state)) -> IndexingManager:
    return IndexingManager(
        chunker=state.chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )


def _get_rag_manager(state: AppState = Depends(get_state)) -> RAGManager:
    if state.pipeline is None:
        raise HTTPException(status_code=500, detail="RAG pipeline not initialized")
    return RAGManager(
        pipeline=state.pipeline,
        llm=state.llm,
        vector_store=state.vector_store,
        embedder=state.embedder,
        reranker=state.reranker,
    )


@router.post(
    "/index", response_model=IndexResponse, dependencies=[Depends(require_api_key)]
)
async def index_documents(
    req: IndexRequest,
    manager: IndexingManager = Depends(_get_indexing_manager),
    state: AppState = Depends(get_state),
) -> IndexResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    result = await manager.index_documents(req.documents, namespace=namespace)
    # Auto-save after indexing
    index_path = getattr(state.config.vector_store, "index_path", None)
    if index_path:
        try:
            await manager.save_index(index_path, namespace=namespace)
        except Exception as e:
            result["errors"].append(f"Auto-save failed: {e}")
    return IndexResponse(**result, namespace=namespace)


@router.post(
    "/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)]
)
async def query_rag(
    req: QueryRequest,
    manager: RAGManager = Depends(_get_rag_manager),
    state: AppState = Depends(get_state),
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


@router.post(
    "/delete", response_model=DeleteResponse, dependencies=[Depends(require_api_key)]
)
async def delete_chunks(
    req: DeleteRequest,
    state: AppState = Depends(get_state),
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
    except Exception as e:
        errors.append(str(e))
    return DeleteResponse(deleted_chunks=deleted, errors=errors)


@router.get("/health", response_model=HealthResponse)
async def rag_health(
    manager: RAGManager = Depends(_get_rag_manager),
    state: AppState = Depends(get_state),
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
    state: AppState = Depends(get_state),
) -> NamespaceListResponse:
    index_path = getattr(state.config.vector_store, "index_path", None)
    namespaces: list[str] = []
    if index_path:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
        except Exception:
            pass
    if not namespaces:
        namespaces = ["default"]
    return NamespaceListResponse(namespaces=namespaces)


@router.post("/save-chat", response_model=None, dependencies=[Depends(require_api_key)])
async def save_chat(
    req: dict[str, Any],
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Save chat content to documents folder and index it."""
    namespace = req.get("namespace", "personal")
    filename = req.get("filename", "chat.md")
    content = req.get("content", "")

    # Validate namespace
    if namespace not in ("personal", "work", "other"):
        raise HTTPException(
            status_code=400, detail="Invalid namespace. Use: personal, work, other"
        )

    # Save to documents folder
    folder = DOCUMENTS_ROOT / namespace
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename

    try:
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

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
            await manager.save_index(index_path, namespace=namespace)

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


@router.post("/reindex", response_model=None, dependencies=[Depends(require_api_key)])
async def reindex_documents(
    req: dict[str, Any],
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Reindex documents from folders. Called from UI button."""
    folder = req.get("folder")
    clear = req.get("clear", False)

    # Run index_documents.py script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "index_documents.py"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail="index_documents.py not found")

    cmd = [sys.executable, str(script_path)]
    if folder:
        cmd.extend(["--folder", folder])
    if clear:
        cmd.append("--clear")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=300
        )
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # Parse output
        output = stdout
        errors: list[str] = []
        results: dict[str, Any] = {}

        if proc.returncode != 0:
            errors.append(stderr or "Unknown error")

        # Parse simple output format: "[namespace] X docs, Y chunks"
        for line in output.split("\n"):
            if "Done:" in line:
                parts = line.strip().split()
                if len(parts) >= 4:
                    ns = parts[0].strip("[]")
                    try:
                        idx = parts.index("docs,")
                        docs = int(parts[idx - 1])
                        chunks = int(parts[idx + 1])
                        results[ns] = {"indexed": docs, "chunks": chunks}
                    except (ValueError, IndexError):
                        pass

        return {
            "success": proc.returncode == 0,
            "results": results,
            "errors": errors,
            "output": output,
        }

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Indexing timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")
