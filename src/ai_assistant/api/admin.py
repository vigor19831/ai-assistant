"""Admin endpoints — diagnostics and runtime config updates."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_assistant.api.deps import AppState, get_state
from ai_assistant.api.security import set_api_key

__all__ = ["router"]

router = APIRouter(prefix="/admin", tags=["admin"])


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
    """Return currently configured model info from config.yaml."""
    cfg = state.config.llm
    return _CurrentModelResponse(
        model=getattr(cfg, "model", "unknown"),
        provider=cfg.provider,
    )


@router.post("/api-key", response_model=_UpdateApiKeyResponse)
async def update_api_key(
    req: _UpdateApiKeyRequest,
    state: Annotated[AppState, Depends(get_state)],
) -> _UpdateApiKeyResponse:
    """Runtime API key rotation. Sets override key in security module.

    Setting api_key to None clears the override and falls back to env var.
    """
    if req.api_key is not None and not req.api_key:
        raise HTTPException(status_code=400, detail="api_key must be non-empty or None")

    set_api_key(req.api_key)
    # Also update the in-memory config for consistency
    state.config.security.api_key = req.api_key

    source = "runtime_override" if req.api_key is not None else "env_var_or_none"
    return _UpdateApiKeyResponse(updated=True, source=source)
