"""Admin endpoints — diagnostics and runtime config updates."""

from __future__ import annotations

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
        "SECURITY_AUDIT: api_key_changed actor=admin_endpoint source=%s",
        source,
        extra={
            "security_event": "api_key_changed",
            "actor": "admin_endpoint",
            "source": source,
            "key_present": req.api_key is not None,
        },
    )
    return _UpdateApiKeyResponse(updated=True, source=source)
