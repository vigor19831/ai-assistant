"""Auto-discovery router assembly."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ai_assistant.api import admin
from ai_assistant.api.security import require_api_key
from ai_assistant.core.logger import get_logger

# Explicit feature handler imports — import errors surface at compile time
# instead of being deferred to the first HTTP request.
from ai_assistant.features.chat import handlers as _chat_handlers
from ai_assistant.features.image_analysis import handlers as _image_analysis_handlers
from ai_assistant.features.rag import handlers as _rag_handlers

__all__ = ["assemble_routers"]

_logger = get_logger("router")

# Registry of explicitly imported feature handler modules.
# Add new features here so that missing handlers.py fails immediately on import.
_FEATURE_HANDLERS = [
    _chat_handlers,
    _image_analysis_handlers,
    _rag_handlers,
]


def assemble_routers() -> list[APIRouter]:
    """Collect routers from explicitly imported feature handlers + admin."""
    routers: list[APIRouter] = []

    routers.append(admin.router)

    for module in _FEATURE_HANDLERS:
        for attr_name in ("router", "router_oai", "router_legacy"):
            router = getattr(module, attr_name, None)
            if isinstance(router, APIRouter):
                routers.append(router)
                _logger.debug(
                    "Loaded router %s from %s",
                    attr_name,
                    module.__name__,
                )

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
