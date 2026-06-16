"""Auto-discovery router assembly."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ai_assistant.api import admin
from ai_assistant.api.security import require_api_key
from ai_assistant.core.metrics import get_metrics, get_metrics_json

from fastapi import Response

# Explicit feature handler imports — import errors surface at compile time
# instead of being deferred to the first HTTP request.
from ai_assistant.features.chat import handlers as chat_handlers
from ai_assistant.features.rag import handlers as rag_handlers

__all__ = ["assemble_routers"]

# Tags for routers that stay at root (no /api/v1 prefix, no API key).
_ROOT_TAGS: frozenset[str] = frozenset({"chat-oai", "metrics"})

# Metrics router — no API key, Prometheus-compatible exposition format
_metrics_router = APIRouter(tags=["metrics"])


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


def assemble_routers() -> list[APIRouter]:
    """Collect routers from explicitly imported feature handlers + admin."""
    routers = list(_ROUTERS)

    # Wrap each router with API key dependency and apply /api/v1 prefix
    # OpenAI-compatible routers (tagged with _OAI_TAG) stay at root without wrapping
    wrapped: list[APIRouter] = []
    for router in routers:
        is_root = any(tag in _ROOT_TAGS for tag in router.tags)
        if is_root:
            # Root routers keep their original paths, no prefix, no extra wrapper
            wrapped.append(router)
        else:
            # Legacy routers get /api/v1 prefix + API key dependency via wrapper
            wrapper = APIRouter(dependencies=[Depends(require_api_key)])
            wrapper.include_router(router, prefix="/api/v1")
            wrapped.append(wrapper)

    return wrapped
