"""Static file mounting — pure HTTP concern."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["mount_static"]


def mount_static(app: FastAPI, config: Any) -> None:
    """Mount /ui once, only if directory exists."""
    if getattr(app.state, "static_mounted", False):
        return
    ui_cfg = config.ui
    static_dir = Path(ui_cfg.static_path)
    if not static_dir.is_absolute():
        static_dir = Path(__file__).parent.parent / static_dir
    if static_dir.exists():
        app.mount(
            "/ui",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
        app.state.static_mounted = True
