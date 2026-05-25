"""Admin endpoints — diagnostics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ai_assistant.api.deps import AppState, get_state

__all__ = ["router"]

router = APIRouter(prefix="/admin", tags=["admin"])


class _CurrentModelResponse(BaseModel):
    model: str
    provider: str


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
