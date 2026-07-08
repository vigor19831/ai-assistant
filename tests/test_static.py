"""Tests for api/static.py — static file mounting."""

from __future__ import annotations

from pathlib import Path
import uuid

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

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


def test_mount_static_relative_path(tmp_path: Path, monkeypatch) -> None:
    """Relative static_path is resolved against package parent."""
    app = FastAPI()
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    # static.py resolves relative paths against Path(__file__).parent.parent
    # (the package parent directory), not cwd.  To test this without
    # depending on the real source tree or the current working directory,
    # we monkeypatch __file__ so the anchor becomes tmp_path.
    fake_module = tmp_path / "api" / "static.py"
    fake_module.parent.mkdir(parents=True)
    import ai_assistant.api.static as _static_module

    monkeypatch.setattr(
        _static_module,
        "__file__",
        str(fake_module),
    )

    # "ui" is relative to tmp_path, which is now the fake package parent.
    config = _make_config("ui")
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
    assert getattr(app.state, "static_mounted", False) is False


def test_mount_static_mounts_at_ui_path(tmp_path: Path) -> None:
    """StaticFiles is mounted at /ui path."""
    app = FastAPI()
    ui_dir = tmp_path / f"ui_{uuid.uuid4().hex}"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    config = _make_config(str(ui_dir))
    mount_static(app, config)
    assert app.state.static_mounted is True
    # Verify mount exists by inspecting routes
    mount_routes = [
        r for r in app.routes if isinstance(r, Mount) and r.path == "/ui"
    ]
    assert len(mount_routes) == 1


def test_mount_static_uses_html_mode(tmp_path: Path) -> None:
    """StaticFiles is mounted with html=True for SPA support."""
    app = FastAPI()
    ui_dir = tmp_path / f"ui_html_{uuid.uuid4().hex}"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>")

    config = _make_config(str(ui_dir))
    mount_static(app, config)

    mount_route = next(
        (r for r in app.routes if isinstance(r, Mount) and r.path == "/ui"),
        None,
    )
    assert mount_route is not None
    assert isinstance(mount_route.app, StaticFiles)
    # Starlette stores the html parameter as an instance attribute.
    assert getattr(mount_route.app, "html", False) is True


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
