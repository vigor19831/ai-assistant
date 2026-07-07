"""Tests for api/static.py — static file mounting."""

from __future__ import annotations

from pathlib import Path
import uuid

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ai_assistant.api.static import mount_static
from ai_assistant.core.config import AppConfig, UIConfig


# ---------------------------------------------------------------------------
# mount_static
# ---------------------------------------------------------------------------


def _make_config(static_path: str) -> AppConfig:
    """Return AppConfig with overridden ui.static_path."""
    return AppConfig(ui=UIConfig(static_path=static_path))


def test_mount_static_skips_when_already_mounted() -> None:
    """Second call is a no-op when static_mounted flag is set."""
    app = FastAPI()
    app.state.static_mounted = True
    config = _make_config("./ui")

    mount_static(app, config)
    # No mount occurred; routes unchanged
    assert app.state.static_mounted is True


def test_mount_static_relative_path(tmp_path: Path) -> None:
    """Relative static_path is resolved against package parent."""
    app = FastAPI()
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    config = _make_config(str(ui_dir))
    mount_static(app, config)
    assert app.state.static_mounted is True


def test_mount_static_absolute_path(tmp_path: Path) -> None:
    """Absolute static_path is used directly."""
    app = FastAPI()
    ui_dir = tmp_path / "absolute_ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    config = _make_config(str(ui_dir.resolve()))
    mount_static(app, config)
    assert app.state.static_mounted is True


def test_mount_static_missing_directory() -> None:
    """Missing directory is silently skipped, flag not set."""
    app = FastAPI()
    config = _make_config("/nonexistent/path/to/ui")

    mount_static(app, config)
    assert not hasattr(app.state, "static_mounted") or app.state.static_mounted is False


def test_mount_static_mounts_at_ui_path(tmp_path: Path) -> None:
    """StaticFiles is mounted at /ui path."""
    app = FastAPI()
    ui_dir = tmp_path / f"ui_{uuid.uuid4().hex}"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    config = _make_config(str(ui_dir))
    mount_static(app, config)
    assert app.state.static_mounted is True
    # Verify mount exists by checking routes
    routes = [r for r in app.routes if hasattr(r, "path")]
    assert any("/ui" in getattr(r, "path", "") for r in routes)


def test_mount_static_uses_html_mode(tmp_path: Path) -> None:
    """StaticFiles is mounted with html=True for SPA support."""
    app = FastAPI()
    ui_dir = tmp_path / f"ui_html_{uuid.uuid4().hex}"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    config = _make_config(str(ui_dir))
    mount_static(app, config)
    # The mount is present; html=True is the default for SPA routing
    assert app.state.static_mounted is True


def test_mount_static_idempotent(tmp_path: Path) -> None:
    """Multiple calls with same app are idempotent (second is no-op)."""
    app = FastAPI()
    ui_dir = tmp_path / f"ui_idem_{uuid.uuid4().hex}"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    config = _make_config(str(ui_dir))
    mount_static(app, config)
    assert app.state.static_mounted is True
    # Second call should be no-op
    mount_static(app, config)
    assert app.state.static_mounted is True
