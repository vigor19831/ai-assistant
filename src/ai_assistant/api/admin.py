"""Admin endpoints — diagnostics and runtime config updates."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_assistant.api.deps import AppState, get_state
from ai_assistant.api.security import require_api_key, set_api_key
from ai_assistant.core.logger import get_logger

_admin_logger = get_logger("admin")

__all__ = ["router"]

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_api_key)],
)


class _CurrentModelResponse(BaseModel):
    model: str
    provider: str


class _UpdateApiKeyRequest(BaseModel):
    api_key: str | None = None


class _UpdateApiKeyResponse(BaseModel):
    updated: bool
    source: str


class _ReloadIndicesResponse(BaseModel):
    reloaded: int
    skipped: int
    errors: list[str]


@router.post("/reload-indices", response_model=_ReloadIndicesResponse)
async def reload_indices(
    state: Annotated[AppState, Depends(get_state)],
) -> _ReloadIndicesResponse:
    """Reload all vector store indices from disk.

    Use this after external indexing (e.g. index_documents.py script)
    to make newly indexed documents searchable without restarting the server.
    """
    if not state.config.security.admin_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    vector_store = state.vector_store
    if vector_store is None:
        raise HTTPException(status_code=503, detail="Vector store not initialized")

    index_path = vector_store.index_path
    reloaded = 0
    skipped = 0
    errors: list[str] = []

    try:
        namespaces = await vector_store.list_namespaces(index_path)
    except Exception as exc:
        _admin_logger.exception("Failed to list namespaces for reload")
        raise HTTPException(status_code=500, detail=f"Failed to list namespaces: {exc}") from exc

    for ns in namespaces:
        try:
            await asyncio.wait_for(
                vector_store.load(index_path, namespace=ns),
                timeout=10.0,
            )
            reloaded += 1
            _admin_logger.info("Reloaded index", extra={"namespace": ns})
        except TimeoutError:
            skipped += 1
            errors.append(f"{ns}: timeout")
            _admin_logger.error(
                "Index reload timed out",
                extra={"namespace": ns},
            )
        except Exception as exc:
            skipped += 1
            errors.append(f"{ns}: {exc}")
            _admin_logger.error(
                "Index reload failed",
                extra={"namespace": ns, "error": str(exc)},
            )

    return _ReloadIndicesResponse(
        reloaded=reloaded,
        skipped=skipped,
        errors=errors,
    )


@router.get("/current-model", response_model=_CurrentModelResponse)
async def get_current_model(
    state: Annotated[AppState, Depends(get_state)],
) -> _CurrentModelResponse:
    if not state.config.security.admin_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    cfg = state.config.llm
    return _CurrentModelResponse(
        model=cfg.model,
        provider=cfg.provider,
    )


@router.post("/api-key", response_model=_UpdateApiKeyResponse)
async def update_api_key(
    req: _UpdateApiKeyRequest,
    state: Annotated[AppState, Depends(get_state)],
) -> _UpdateApiKeyResponse:
    if not state.config.security.admin_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    if req.api_key is not None and not req.api_key:
        raise HTTPException(status_code=400, detail="api_key must be non-empty or None")
    set_api_key(req.api_key)
    source = "runtime_override" if req.api_key is not None else "env_var_or_none"
    _admin_logger.warning(
        f"SECURITY_AUDIT: api_key_changed actor=admin_endpoint source={source}",
        extra={
            "security_event": "api_key_changed",
            "actor": "admin_endpoint",
            "source": source,
            "key_present": req.api_key is not None,
        },
    )
    return _UpdateApiKeyResponse(updated=True, source=source)
