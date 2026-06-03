"""Auto-discovery router assembly."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ai_assistant.api import admin
from ai_assistant.api.security import require_api_key

# Explicit feature handler imports — import errors surface at compile time
# instead of being deferred to the first HTTP request.
from ai_assistant.features.chat import handlers as _chat_handlers
from ai_assistant.features.rag import handlers as _rag_handlers

__all__ = ["assemble_routers"]

# Explicit router registry — missing handlers fail immediately at import time.
# Add new routers here when adding feature handlers.
_ROUTERS: list[APIRouter] = [
    admin.router,
    _chat_handlers.router,
    _chat_handlers.router_oai,
    _rag_handlers.router,
]


def assemble_routers() -> list[APIRouter]:
    """Collect routers from explicitly imported feature handlers + admin."""
    routers = list(_ROUTERS)

    # Wrap each router with API key dependency and apply /api/v1 prefix
    # OpenAI-compatible routers (tagged "chat-oai") stay at root without wrapping
    wrapped: list[APIRouter] = []
    for router in routers:
        is_oai = "chat-oai" in router.tags
        if is_oai:
            # OpenAI routers keep their original paths, no prefix, no extra wrapper
            wrapped.append(router)
        else:
            # Legacy routers get /api/v1 prefix + API key dependency via wrapper
            wrapper = APIRouter(dependencies=[Depends(require_api_key)])
            wrapper.include_router(router, prefix="/api/v1")
            wrapped.append(wrapper)

    return wrapped
