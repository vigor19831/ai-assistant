"""Auto-discovery router assembly."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from api import admin
from api.security import require_api_key

logger = logging.getLogger("ai_assistant.router")


def assemble_routers() -> list[APIRouter]:
    """Auto-discover and collect routers from features/*/handlers.py + admin."""
    routers: list[APIRouter] = []

    # 1. Admin router (manual, not auto-discovered)
    routers.append(admin.router)

    # 2. Auto-discovered feature routers
    features_dir = Path(__file__).parent.parent / "features"
    if not features_dir.exists():
        return routers

    for feature_dir in features_dir.iterdir():
        if not feature_dir.is_dir() or feature_dir.name.startswith("_"):
            continue
        handlers_path = feature_dir / "handlers.py"
        if not handlers_path.exists():
            continue
        try:
            module = importlib.import_module(f"features.{feature_dir.name}.handlers")
            router = getattr(module, "router", None)
            if isinstance(router, APIRouter):
                routers.append(router)
                logger.debug(
                    "Loaded router from features.%s.handlers", feature_dir.name
                )
            else:
                logger.warning(
                    "No 'router' found in features.%s.handlers", feature_dir.name
                )
        except Exception as e:
            logger.error("Failed to load features.%s.handlers: %s", feature_dir.name, e)
            continue

    # 3. Enforce API key on every router (defence in depth)
    for router in routers:
        router.dependencies.append(Depends(require_api_key))

    return routers
