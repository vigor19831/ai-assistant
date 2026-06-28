"""Auto-discovery router assembly."""

from __future__ import annotations

import time
from importlib.metadata import version as _get_version
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from starlette.requests import Request  # noqa: TC002

from ai_assistant.api import admin
from ai_assistant.api.security import (
    SECURITY_MAX_BODY,
    check_request_size,
    require_api_key,
)
from ai_assistant.core.config import SecurityConfig
from ai_assistant.core.metrics import get_metrics, get_metrics_json

# Explicit feature handler imports — import errors surface at compile time
# instead of being deferred to the first HTTP request.
from ai_assistant.features.chat import handlers as chat_handlers
from ai_assistant.features.rag import handlers as rag_handlers

__all__ = ["assemble_routers"]

# Tags for routers that stay at root (no /api/v1 prefix).
# Admin has its own auth and admin_enabled gate.
_ROOT_TAGS: frozenset[str] = frozenset({"chat-oai", "metrics", "admin"})

# Metrics router — no API key, Prometheus-compatible exposition format
_metrics_router = APIRouter(tags=["metrics"])

_START_TIME = time.time()


def _load_version() -> str:
    """Read version from installed package metadata (stdlib, works in wheel)."""
    try:
        return _get_version("ai-assistant")
    except Exception:
        return "unknown"


_VERSION = _load_version()


class _HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float


@_metrics_router.get("/health", response_model=_HealthResponse)
async def _health_endpoint() -> _HealthResponse:
    return _HealthResponse(
        status="ok",
        version=_VERSION,
        uptime_seconds=round(time.time() - _START_TIME, 2),
    )


@_metrics_router.get("/metrics", response_class=Response)
async def _metrics_endpoint() -> Response:
    return Response(content=get_metrics(), media_type="text/plain; version=0.0.4")

@_metrics_router.get("/metrics/json")
async def _metrics_json_endpoint() -> dict[str, Any]:
    return get_metrics_json()


# Explicit router registry — missing handlers fail immediately at import time.
# Add new routers here when adding feature handlers.
_ROUTERS: list[APIRouter] = [
    _metrics_router,
    admin.router,
    chat_handlers.router,
    chat_handlers.router_oai,
    rag_handlers.router,
]


def assemble_routers(security: SecurityConfig | None = None) -> list[APIRouter]:
    """Collect routers from explicitly imported feature handlers + admin.

    Args:
        security: Security configuration. If *openai_routes_require_auth* is True,
            OpenAI-compatible routes (chat-oai) will require API key auth.
    """
    routers = list(_ROUTERS)

    # Determine which root-tagged routers require protection
    protected_root_tags: set[str] = set()
    if security is not None and security.openai_routes_require_auth:
        protected_root_tags.add("chat-oai")
    # Metrics always stays unprotected
    always_unprotected: frozenset[str] = frozenset({"metrics"})

    # Body size limit from config; fallback to module default if no security config
    _max_body: int = security.max_body_size if security is not None else SECURITY_MAX_BODY

    async def _size_check(request: Request) -> None:
        """Inject configured max body size into check_request_size."""
        await check_request_size(request, max_sz=_max_body)

    wrapped: list[APIRouter] = []
    for router in routers:
        is_root = any(tag in _ROOT_TAGS for tag in router.tags)
        is_always_unprotected = any(
            tag in always_unprotected for tag in router.tags
        )
        is_protected_root = any(
            tag in protected_root_tags for tag in router.tags
        )

        if is_always_unprotected:
            # Metrics always stays unprotected
            wrapped.append(router)
        elif not is_root:
            # Legacy routers get /api/v1 prefix + API key + body size check
            wrapper = APIRouter(dependencies=[
                Depends(require_api_key),
                Depends(_size_check),
            ])
            wrapper.include_router(router, prefix="/api/v1")
            wrapped.append(wrapper)
        elif is_protected_root:
            # Root router that needs auth: wrap with dependency, no prefix
            wrapper = APIRouter(dependencies=[
                Depends(require_api_key),
                Depends(_size_check),
            ])
            wrapper.include_router(router)
            wrapped.append(wrapper)
        else:
            # Root routers keep their original paths, no prefix, no extra wrapper
            wrapped.append(router)

    return wrapped
