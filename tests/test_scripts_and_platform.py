"""Tests for launcher.py.

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
_LAUNCHER_PATH = _DEV_DIR / "launcher.py"

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


def load_launcher() -> object:
    if "launcher" not in _MODULE_CACHE:
        _MODULE_CACHE["launcher"] = _import_from_path("_test_launcher", _LAUNCHER_PATH)
    return _MODULE_CACHE["launcher"]


# ── launcher helpers ──

class TestLauncherHelpers:
    def test_sort_scripts_order(self):
        launcher = load_launcher()
        files = [
            Path("scripts/clean_cache.py"),
            Path("scripts/start.py"),
            Path("scripts/z_last.py"),
        ]
        sorted_names = [p.stem for p in launcher.sort_scripts(files)]
        assert sorted_names == ["start", "clean_cache", "z_last"]

    def test_get_python_venv_exists(self, tmp_path):
        launcher = load_launcher()
        venv = tmp_path / ".venv"
        sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        (venv / sub).parent.mkdir(parents=True)
        (venv / sub).touch()
        assert ".venv" in launcher.get_python(tmp_path)

    def test_get_python_raises_when_venv_missing(self, tmp_path):
        launcher = load_launcher()
        with pytest.raises(FileNotFoundError):
            launcher.get_python(tmp_path)

    def test_get_python_returns_venv_python_when_exists(self, tmp_path):
        launcher = load_launcher()
        venv_bin = tmp_path / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        venv_bin.mkdir(parents=True)
        fake_python = venv_bin / ("python.exe" if os.name == "nt" else "python")
        fake_python.touch()
        fake_python.chmod(0o755)
        result = launcher.get_python(tmp_path)
        assert result == str(fake_python)

    def test_collect_skips_init(self, tmp_path):
        launcher = load_launcher()
        d = tmp_path / "scripts"
        d.mkdir()
        (d / "a.py").write_text("pass")
        (d / "__init__.py").write_text("")
        result = launcher.collect(tmp_path, "scripts")
        assert len(result) == 1
        assert result[0].name == "a.py"

    def test_collect_empty_when_missing(self, tmp_path):
        launcher = load_launcher()
        result = launcher.collect(tmp_path, "nonexistent")
        assert result == []


class TestLauncherMenu:
    def test_print_menu_two_columns(self, capsys):
        launcher = load_launcher()
        scripts = [(1, "start.py", "scripts/start.py")]
        tests = [(2, "test_foo.py", "tests/test_foo.py")]
        launcher.print_menu(scripts, tests, last=1)
        out = capsys.readouterr().out
        assert "SCRIPTS" in out
        assert "TESTS" in out
        assert "[ 1] * start.py" in out
        assert "[ 2] test_foo.py" in out
        assert "[r]  Rerun last" in out
        assert "[0]  Exit" in out

    def test_print_menu_uneven_lists(self, capsys):
        launcher = load_launcher()
        scripts = [
            (1, "a.py", "scripts/a.py"),
            (2, "b.py", "scripts/b.py"),
        ]
        tests = [(3, "test_x.py", "tests/test_x.py")]
        launcher.print_menu(scripts, tests, last=None)
        out = capsys.readouterr().out
        assert "[ 1] a.py" in out
        assert "[ 2] b.py" in out
        assert "[ 3] test_x.py" in out


class TestLauncherFindTarget:
    def test_find_target_in_scripts(self):
        launcher = load_launcher()
        scripts = [(1, "a.py", "scripts/a.py")]
        tests = [(2, "b.py", "tests/b.py")]
        label, target = launcher.find_target(1, scripts, tests)
        assert label == "a.py"
        assert target == "scripts/a.py"

    def test_find_target_in_tests(self):
        launcher = load_launcher()
        scripts = [(1, "a.py", "scripts/a.py")]
        tests = [(2, "b.py", "tests/b.py")]
        label, target = launcher.find_target(2, scripts, tests)
        assert label == "b.py"
        assert target == "tests/b.py"

    def test_find_target_not_found(self):
        launcher = load_launcher()
        scripts = [(1, "a.py", "scripts/a.py")]
        tests = []
        label, target = launcher.find_target(99, scripts, tests)
        assert label is None
        assert target is None


class TestLauncherRun:
    def test_run_executes_subprocess(self, tmp_path, monkeypatch):
        launcher = load_launcher()
        monkeypatch.chdir(tmp_path)
        py = sys.executable

        script = tmp_path / "dummy.py"
        script.write_text("import sys; print('hello', sys.argv[1:])\n")

        run_calls = []

        def mock_run(cmd, **kwargs):
            run_calls.append((cmd, kwargs.get("cwd")))
            class MockRes:
                returncode = 0
            return MockRes()

        monkeypatch.setattr(launcher.subprocess, "run", mock_run)
        monkeypatch.setattr("builtins.input", lambda _: "")

        rc = launcher.run(py, str(script), tmp_path, ["--flag", "value"])
        assert rc == 0
        assert len(run_calls) == 1
        cmd, cwd = run_calls[0]
        assert cmd[0] == py
        assert cmd[1] == str(script)
        assert "--flag" in cmd
        assert "value" in cmd
        assert cwd == tmp_path


class TestLauncherNoMenu:
    def test_no_menu_flag_parses(self):
        launcher = load_launcher()
        parser = launcher.argparse.ArgumentParser()
        parser.add_argument("--no-menu", action="store_true")
        parser.add_argument("target", nargs="?")
        parser.add_argument("extra", nargs=launcher.argparse.REMAINDER)
        args = parser.parse_args(["--no-menu", "1", "--", "--compact"])
        assert args.no_menu is True
        assert args.target == "1"
        assert args.extra == ["--compact"]

    def test_no_menu_runs_target(self, tmp_path, monkeypatch):
        launcher = load_launcher()
        monkeypatch.chdir(tmp_path)
        py = sys.executable

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        dummy = scripts_dir / "dummy.py"
        dummy.write_text("print('ok')\n")

        run_calls = []

        def mock_run(cmd, **kwargs):
            run_calls.append(cmd)
            class MockRes:
                returncode = 0
            return MockRes()

        monkeypatch.setattr(launcher.subprocess, "run", mock_run)
        monkeypatch.setattr("builtins.input", lambda _: "")

        scripts = [(1, "dummy.py", str(dummy))]
        tests = []
        label, target = launcher.find_target(1, scripts, tests)
        assert target == str(dummy)
        rc = launcher.run(py, target, tmp_path, [])
        assert rc == 0
        assert len(run_calls) == 1


class TestLauncherMinimal:
    def test_no_removed_bloat(self):
        """Ensure old heavy features are truly gone."""
        launcher = load_launcher()
        removed = [
            "ask_flags", "ask_context_build_mode", "ask_audit_mode",
            "ask_test_mode", "flag_hint", "TEST_FLAGS", "BACKGROUND",
            "run_bg", "run_terminal", "_shutdown", "_sanitize_extra",
            "_get_server_port", "TARGET_TERMINAL", "TERMINAL_CMD",
            "enable_ansi", "pad_ansi", "timestamp", "TEST_MODES",
        ]
        for name in removed:
            assert not hasattr(launcher, name), f"{name} should be removed"
