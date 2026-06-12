"""Tests for run.py.

All script imports are isolated via importlib.util to avoid sys.path pollution.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# ── isolated script loader ──

_DEV_DIR = Path(__file__).resolve().parent.parent
_RUN_PATH = _DEV_DIR / "run.py"

_MODULE_CACHE: dict[str, object] = {}


def _import_from_path(module_name: str, file_path: Path) -> object:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_run() -> object:
    if "run" not in _MODULE_CACHE:
        _MODULE_CACHE["run"] = _import_from_path("_test_run", _RUN_PATH)
    return _MODULE_CACHE["run"]


# ── run.py helpers ──

class TestRunHelpers:
    def test_port_free_true_when_no_server(self):
        run = load_run()
        # Use a very high port unlikely to be in use
        assert run.port_free(65432) is True

    def test_port_free_false_when_port_in_use(self):
        run = load_run()
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            _, port = sock.getsockname()
            sock.listen(1)
            assert run.port_free(port) is False
        finally:
            sock.close()

    def test_wait_port_timeout(self):
        run = load_run()
        # Port 65433 should be free, so wait_port returns False after timeout
        result = run.wait_port(65433, timeout=0.1)
        assert result is False

    def test_check_venv_returns_path_when_exists(self, tmp_path):
        run = load_run()
        venv = tmp_path / ".venv"
        sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        (venv / sub).parent.mkdir(parents=True)
        (venv / sub).touch()
        result = run._check_venv()
        assert ".venv" in str(result)

    def test_find_model_returns_none_when_no_vendor(self):
        run = load_run()
        result = run._find_model("nonexistent")
        assert result is None

    def test_find_model_finds_gguf(self, tmp_path, monkeypatch):
        run = load_run()
        monkeypatch.setattr(run, "ROOT", tmp_path)
        models_dir = tmp_path / "vendor" / "models"
        models_dir.mkdir(parents=True)
        (models_dir / "test-model.gguf").write_text("fake")
        result = run._find_model("test-model")
        assert result is not None
        assert result.name == "test-model.gguf"

    def test_load_config_empty_when_no_file(self, tmp_path, monkeypatch):
        run = load_run()
        monkeypatch.setattr(run, "ROOT", tmp_path)
        result = run._load_config()
        assert result == {}

    def test_load_config_reads_yaml(self, tmp_path, monkeypatch):
        run = load_run()
        monkeypatch.setattr(run, "ROOT", tmp_path)
        config = tmp_path / "config.yaml"
        config.write_text("llm:\n  model: test-model\n")
        result = run._load_config()
        assert result["llm"]["model"] == "test-model"


class TestRunConstants:
    def test_venv_path_crossplatform(self):
        run = load_run()
        venv_py = run.VENV_PY
        if os.name == "nt":
            assert "Scripts" in str(venv_py)
            assert venv_py.name == "python.exe"
        else:
            assert "bin" in str(venv_py)
            assert venv_py.name == "python"

    def test_root_is_absolute(self):
        run = load_run()
        assert run.ROOT.is_absolute()


class TestRunMinimal:
    def test_no_removed_bloat(self):
        """Ensure old heavy features are truly gone."""
        run = load_run()
        removed = [
            "ask_flags", "ask_context_build_mode", "ask_audit_mode",
            "ask_test_mode", "flag_hint", "TEST_FLAGS", "BACKGROUND",
            "run_bg", "run_terminal", "_shutdown", "_sanitize_extra",
            "_get_server_port", "TARGET_TERMINAL", "TERMINAL_CMD",
            "enable_ansi", "pad_ansi", "timestamp", "TEST_MODES",
            "sort_scripts", "collect", "print_menu", "find_target",
        ]
        for name in removed:
            assert not hasattr(run, name), f"{name} should be removed"
