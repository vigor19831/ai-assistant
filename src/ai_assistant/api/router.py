"""Auto-discovery router assembly."""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import APIRouter, Depends

from ai_assistant.api import admin
from ai_assistant.api.security import require_api_key
from ai_assistant.core.logger import get_logger

__all__ = ["assemble_routers"]

_logger = get_logger("router")


def assemble_routers() -> list[APIRouter]:
    """Auto-discover and collect routers from features/*/handlers.py + admin."""
    routers: list[APIRouter] = []

    routers.append(admin.router)

    features_dir = Path(__file__).parent.parent / "features"
    if not features_dir.exists():
        return []

    for feature_dir in features_dir.iterdir():
        if not feature_dir.is_dir() or feature_dir.name.startswith("_"):
            continue
        handlers_path = feature_dir / "handlers.py"
        if not handlers_path.exists():
            continue
        try:
            module = importlib.import_module(
                f"ai_assistant.features.{feature_dir.name}.handlers"
            )
            for attr_name in ("router", "router_oai", "router_legacy"):
                router = getattr(module, attr_name, None)
                if isinstance(router, APIRouter):
                    routers.append(router)
                    _logger.debug(
                        "Loaded router %s from features.%s.handlers",
                        attr_name,
                        feature_dir.name,
                    )
        except Exception as exc:
            _logger.error(
                "Failed to load features.%s.handlers: %s",
                feature_dir.name,
                exc,
            )
            continue

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
