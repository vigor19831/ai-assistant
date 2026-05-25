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
        return routers

    for feature_dir in features_dir.iterdir():
        if not feature_dir.is_dir() or feature_dir.name.startswith("_"):
            continue
        handlers_path = feature_dir / "handlers.py"
        if not handlers_path.exists():
            continue
        try:
            module = importlib.import_module(f"ai_assistant.features.{feature_dir.name}.handlers")
            router = getattr(module, "router", None)
            if isinstance(router, APIRouter):
                routers.append(router)
                _logger.debug(
                    "Loaded router from features.%s.handlers",
                    feature_dir.name,
                )
            else:
                _logger.warning(
                    "No 'router' found in features.%s.handlers",
                    feature_dir.name,
                )
        except Exception as exc:
            _logger.error(
                "Failed to load features.%s.handlers: %s",
                feature_dir.name,
                exc,
            )
            continue

    for router in routers:
        router.dependencies.append(Depends(require_api_key))

    return routers
