"""Static file mounting — pure HTTP concern."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ai_assistant.core.config import AppConfig

__all__ = ["mount_static"]


def mount_static(app: FastAPI, config: AppConfig) -> None:
    """Mount /ui once, only if directory exists and path is safe."""
    if getattr(app.state, "static_mounted", False):
        return
    ui_cfg = config.ui
    static_dir = Path(ui_cfg.static_path)
    if not static_dir.is_absolute():
        _module_file = getattr(sys.modules.get(__name__), "__file__", None)
        if _module_file is None:
            return
        static_dir = Path(_module_file).parent.parent / static_dir

    # Reject path traversal: normalize and check for .. components
    normalized = static_dir.as_posix()
    if ".." in normalized.split("/"):
        return

    if static_dir.exists() and static_dir.is_dir():
        app.mount(
            "/ui",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
        app.state.static_mounted = True
