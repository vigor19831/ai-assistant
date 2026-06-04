"""Tests for launcher.py, check scripts, and Windows-specific behavior.

All script imports are isolated via importlib.util to avoid sys.path pollution.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from dataclasses import make_dataclass
from pathlib import Path

import pytest

# ── isolated script loader (self-contained, no external deps) ──

_DEV_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = _DEV_DIR / "scripts"
_LAUNCHER_PATH = _DEV_DIR / "launcher.py"

_MODULE_CACHE: dict[str, object] = {}


def _import_from_path(module_name: str, file_path: Path) -> object:
    """Import a single file as a module without touching sys.path globally."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_script(name: str) -> object:
    """Import dev/scripts/{name}.py module."""
    if name not in _MODULE_CACHE:
        path = _SCRIPTS_DIR / f"{name}.py"
        _MODULE_CACHE[name] = _import_from_path(f"_test_script_{name}", path)
    return _MODULE_CACHE[name]


def load_launcher() -> object:
    """Import dev/launcher.py module."""
    if "launcher" not in _MODULE_CACHE:
        _MODULE_CACHE["launcher"] = _import_from_path("_test_launcher", _LAUNCHER_PATH)
    return _MODULE_CACHE["launcher"]

# ── launcher helpers ──


class TestLauncherHelpers:
    def test_timestamp_format(self):
        launcher = load_launcher()
        ts = launcher.timestamp()
        assert re.match(r"^\d{2}:\d{2}:\d{2}$", ts)

    def test_pad_ansi_plain(self):
        launcher = load_launcher()
        assert launcher.pad_ansi("hello", 8) == "hello   "

    def test_pad_ansi_with_colors(self):
        launcher = load_launcher()
        green_hello = "\033[32mhello\033[0m"
        padded = launcher.pad_ansi(green_hello, 8)
        assert len(padded) == len(green_hello) + 3

    def test_sort_scripts_order(self):
        launcher = load_launcher()
        files = [
            Path("scripts/clean_cache.py"),
            Path("scripts/start.py"),
            Path("scripts/terminal.py"),
            Path("scripts/z_last.py"),
        ]
        sorted_names = [p.stem for p in launcher.sort_scripts(files)]
        assert sorted_names == ["start", "clean_cache", "terminal", "z_last"]

    def test_flag_hint_known(self):
        launcher = load_launcher()
        assert "--clean" in launcher.flag_hint("scripts/clean_cache.py")

    def test_flag_hint_unknown(self):
        launcher = load_launcher()
        assert launcher.flag_hint("scripts/unknown.py") == ""

    def test_sanitize_extra_valid(self):
        launcher = load_launcher()
        assert launcher._sanitize_extra(["--flag", "value"]) == ["--flag", "value"]

    def test_sanitize_extra_invalid(self):
        launcher = load_launcher()
        assert launcher._sanitize_extra(["bad;cmd"]) is None

    def test_get_python_venv_exists(self, tmp_path):
        launcher = load_launcher()
        venv = tmp_path / ".venv"
        sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        (venv / sub).parent.mkdir(parents=True)
        (venv / sub).touch()
        assert ".venv" in launcher.get_python(tmp_path)

    def test_get_python_raises_when_venv_missing(self, tmp_path):
        """get_python must NEVER fall back to sys.executable."""
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


class TestLauncherMenu:
    def test_print_menu_runs(self, capsys):
        launcher = load_launcher()
        scripts = [(1, "start.py", "scripts/start.py")]
        tests = [(2, "test_all", "pytest:tests")]
        launcher.print_menu(scripts, tests, last=1)
        out = capsys.readouterr().out
        assert "SCRIPTS" in out
        assert "TESTS" in out
        assert "[ 1]" in out


class TestLauncherNoMenu:
    def test_no_menu_flag_parses(self, monkeypatch):
        launcher = load_launcher()

        # Build parser exactly as main() does
        parser = launcher.argparse.ArgumentParser(description="AI Assistant Launcher")
        parser.add_argument(
            "--no-menu", action="store_true", help="Non-interactive mode (CI)"
        )
        parser.add_argument("target", nargs="?", help="Number, 'r', or script name")
        parser.add_argument(
            "extra", nargs=launcher.argparse.REMAINDER, help="Extra arguments after --"
        )

        args = parser.parse_args(["--no-menu", "1"])
        assert args.no_menu is True
        assert args.target == "1"

    def test_run_creates_test_log(self, tmp_path, monkeypatch):
        launcher = load_launcher()
        monkeypatch.chdir(tmp_path)
        py = sys.executable

        # Mock input() so run() doesn't wait for Enter in test environment
        monkeypatch.setattr("builtins.input", lambda _: "")

        # Create a dummy pytest target
        test_dir = tmp_path / "dev" / "tests"
        test_dir.mkdir(parents=True)
        (test_dir / "dummy_test.py").write_text("def test_dummy(): pass\n")

        target = f"pytest:{test_dir}"

        # Mock subprocess.Popen to avoid nested pytest + capture the command
        popen_calls = []
        original_popen = launcher.subprocess.Popen

        def mock_popen(cmd, **kwargs):
            popen_calls.append(cmd)

            # Return a mock process that exits immediately with code 0
            class MockProc:
                stdout = []

                def wait(self):
                    return 0

                @property
                def returncode(self):
                    return 0

            return MockProc()

        monkeypatch.setattr(launcher.subprocess, "Popen", mock_popen)

        result = launcher.run(py, target, tmp_path, [], [])

        # Verify pytest command was constructed correctly
        assert len(popen_calls) == 1
        cmd = popen_calls[0]
        assert "pytest" in cmd
        assert "--tb=long" in cmd
        assert "--color=yes" in cmd
        assert "-v" in cmd

        # Verify log file was created with header
        log_files = list((tmp_path / "dev").glob("tests_run_*.log"))
        assert len(log_files) == 1
        log_content = log_files[0].read_text()
        assert "Test run" in log_content
        assert "Command:" in log_content


class TestLauncherShutdown:
    def test_shutdown_calls_stop(self, tmp_path, monkeypatch):
        launcher = load_launcher()
        monkeypatch.chdir(tmp_path)

        # Create dummy stop.py
        stop_script = tmp_path / "ops" / "scripts" / "stop.py"
        stop_script.parent.mkdir(parents=True)
        stop_script.write_text("print('stopped')\n")

        # Create dummy scripts list
        scripts = [(1, "stop.py", str(stop_script))]
        tests = []

        py = sys.executable
        rc = launcher._shutdown(tmp_path, py, scripts, tests)
        assert rc == 0


# ── check scripts ──


class TestCheckScripts:
    def test_check_mypy_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["check_mypy"])
        check_mypy = load_script("check_mypy")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "dummy.py").write_text("x: int = 1\n")
        try:
            import mypy  # noqa: F401
        except ModuleNotFoundError:
            pytest.skip("mypy not installed")
        rc = check_mypy.main()
        assert rc in (0, 1)  # 0 = clean, 1 = errors found

    def test_check_ruff_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["check_ruff"])
        check_ruff = load_script("check_ruff")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "dummy.py").write_text("x=1\n")
        try:
            import ruff  # noqa: F401
        except ModuleNotFoundError:
            pytest.skip("ruff not installed")
        rc = check_ruff.main()
        assert rc in (0, 1)

    def test_audit_project_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["audit_project"])
        audit = load_script("audit_project")
        monkeypatch.chdir(tmp_path)
        (tmp_path / "src" / "ai_assistant").mkdir(parents=True)
        (tmp_path / "src" / "ai_assistant" / "dummy.py").write_text("x = 1\n")
        rc = audit.main()
        assert rc in (0, 1)

    def test_check_smoke_imports(self):
        check_smoke = load_script("check_smoke")
        state = check_smoke.make_mock_state()
        assert hasattr(state, "llm")
        assert hasattr(state, "config")

    def test_check_mutations_skips_windows(self, monkeypatch):
        check_mutations = load_script("check_mutations")
        monkeypatch.setattr(sys, "platform", "win32")
        assert check_mutations.main() == 0

    def test_check_llm_no_config(self, tmp_path, monkeypatch):
        check_llm = load_script("check_llm")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AI_CONFIG_PATH", raising=False)

        def _fake_load_config(path: str):
            raise FileNotFoundError(f"Config not found: {path}")

        monkeypatch.setattr(check_llm, "load_config", _fake_load_config)
        rc = check_llm.check_llm()
        assert rc == 1


# ── Windows-specific ──


class TestWindowsSpecific:
    @pytest.mark.skipif(os.name != "nt", reason="Windows only")
    def test_ansi_enabled_on_windows(self):
        launcher = load_launcher()
        # Should not raise
        launcher.enable_ansi()

    def test_terminal_cmd_nt(self):
        launcher = load_launcher()
        assert "nt" in launcher.TERMINAL_CMD
        cmd = launcher.TERMINAL_CMD["nt"]("venv", "root")
        assert "cmd" in cmd

    def test_terminal_cmd_posix(self):
        launcher = load_launcher()
        assert "posix" in launcher.TERMINAL_CMD
        cmd = launcher.TERMINAL_CMD["posix"]("venv", "root")
        assert "gnome-terminal" in cmd or "bash" in cmd


class TestLauncherConstants:
    def test_target_terminal_constant(self):
        launcher = load_launcher()
        assert hasattr(launcher, "TARGET_TERMINAL")
        assert launcher.TARGET_TERMINAL == "__terminal__"

    def test_terminal_in_menu(self, capsys):
        launcher = load_launcher()
        scripts = [(1, "TERMINAL (.venv)", launcher.TARGET_TERMINAL)]
        tests = []
        launcher.print_menu(scripts, tests, last=None)
        out = capsys.readouterr().out
        assert "TERMINAL" in out
