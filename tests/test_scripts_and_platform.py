"""Tests for launcher.py, check scripts, and Windows-specific behavior."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
# ── launcher helpers ──


class TestLauncherHelpers:
    def test_timestamp_format(self):
        from launcher import timestamp

        ts = timestamp()
        assert re.match(r"^\d{2}:\d{2}:\d{2}$", ts)

    def test_pad_ansi_plain(self):
        from launcher import pad_ansi

        assert pad_ansi("hello", 8) == "hello   "

    def test_pad_ansi_with_colors(self):
        from launcher import pad_ansi

        green_hello = "\033[32mhello\033[0m"
        padded = pad_ansi(green_hello, 8)
        assert len(padded) == len(green_hello) + 3

    def test_sort_scripts_order(self):
        from launcher import sort_scripts

        files = [
            Path("scripts/clean_cache.py"),
            Path("scripts/start.py"),
            Path("scripts/terminal.py"),
            Path("scripts/z_last.py"),
        ]
        sorted_names = [p.stem for p in sort_scripts(files)]
        assert sorted_names == ["start", "clean_cache", "terminal", "z_last"]

    def test_flag_hint_known(self):
        from launcher import flag_hint

        assert "--clean" in flag_hint("scripts/clean_cache.py")

    def test_flag_hint_unknown(self):
        from launcher import flag_hint

        assert flag_hint("scripts/unknown.py") == ""

    def test_sanitize_extra_valid(self):
        from launcher import _sanitize_extra

        assert _sanitize_extra(["--flag", "value"]) == ["--flag", "value"]

    def test_sanitize_extra_invalid(self):
        from launcher import _sanitize_extra

        assert _sanitize_extra(["bad;cmd"]) is None

    def test_get_python_venv_exists(self, tmp_path):
        from launcher import get_python

        venv = tmp_path / ".venv"
        sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        (venv / sub).parent.mkdir(parents=True)
        (venv / sub).touch()
        assert ".venv" in get_python(tmp_path)

    def test_get_python_fallback(self, tmp_path):
        from launcher import get_python

        assert get_python(tmp_path) == sys.executable

    def test_collect_skips_init(self, tmp_path):
        from launcher import collect

        d = tmp_path / "scripts"
        d.mkdir()
        (d / "a.py").write_text("pass")
        (d / "__init__.py").write_text("")
        result = collect(tmp_path, "scripts")
        assert len(result) == 1
        assert result[0].name == "a.py"


class TestLauncherMenu:
    def test_print_menu_runs(self, capsys):
        from launcher import print_menu

        scripts = [(1, "start.py", "scripts/start.py")]
        tests = [(2, "test_all", "pytest:tests")]
        print_menu(scripts, tests, last=1)
        out = capsys.readouterr().out
        assert "SCRIPTS" in out
        assert "TESTS" in out
        assert "[ 1]" in out


class TestLauncherRun:
    def test_run_bg_creates_pid(self, tmp_path, monkeypatch):
        from launcher import run_bg

        monkeypatch.chdir(tmp_path)
        py = sys.executable
        target = str(tmp_path / "scripts" / "dummy.py")
        (tmp_path / "scripts").mkdir()
        Path(target).write_text("print(1)")
        run_bg(py, target, tmp_path, [])
        pid_file = tmp_path / "data" / "dummy.pid"
        assert pid_file.exists()
        assert pid_file.read_text().strip().isdigit()


# ── check scripts ──


class TestCheckScripts:
    def test_check_mypy_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["check_mypy"])
        from check_mypy import main

        monkeypatch.chdir(tmp_path)
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "dummy.py").write_text("x: int = 1\n")
        try:
            import mypy  # noqa: F401
        except ModuleNotFoundError:
            pytest.skip("mypy not installed")
        rc = main()
        assert rc in (0, 1)  # 0 = clean, 1 = errors found

    def test_check_ruff_runs(self, tmp_path, monkeypatch):
        from check_ruff import main

        monkeypatch.chdir(tmp_path)
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "dummy.py").write_text("x=1\n")
        try:
            import ruff  # noqa: F401
        except ModuleNotFoundError:
            pytest.skip("ruff not installed")
        rc = main()
        assert rc in (0, 1)

    def test_check_vulture_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["check_vulture"])
        from check_vulture import main

        monkeypatch.chdir(tmp_path)
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "dummy.py").write_text("x = 1\n")
        try:
            import vulture  # noqa: F401
        except ModuleNotFoundError:
            pytest.skip("vulture not installed")
        rc = main()
        assert rc in (0, 1)

    def test_check_smoke_imports(self):
        from check_smoke import make_mock_state

        state = make_mock_state()
        assert hasattr(state, "llm")
        assert hasattr(state, "config")

    def test_check_mutations_skips_windows(self, monkeypatch):
        from check_mutations import main

        monkeypatch.setattr(sys, "platform", "win32")
        assert main() == 0

    def test_check_llm_no_config(self, tmp_path, monkeypatch):
        import check_llm

        monkeypatch.setattr(check_llm, "root", tmp_path)
        monkeypatch.setattr(check_llm, "cfg_path", tmp_path / "config.yaml")
        assert not check_llm.cfg_path.exists()


# ── Windows-specific ──


class TestWindowsSpecific:
    @pytest.mark.skipif(os.name != "nt", reason="Windows only")
    def test_ansi_enabled_on_windows(self):
        from launcher import enable_ansi

        # Should not raise
        enable_ansi()

    def test_terminal_cmd_nt(self):
        from launcher import TERMINAL_CMD

        assert "nt" in TERMINAL_CMD
        cmd = TERMINAL_CMD["nt"]("venv", "root")
        assert "cmd" in cmd

    def test_terminal_cmd_posix(self):
        from launcher import TERMINAL_CMD

        assert "posix" in TERMINAL_CMD
        cmd = TERMINAL_CMD["posix"]("venv", "root")
        assert "gnome-terminal" in cmd or "bash" in cmd
