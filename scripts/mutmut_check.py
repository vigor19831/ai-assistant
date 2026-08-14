#!/usr/bin/env python3
"""mutmut_check.py — Mutation testing for critical modules.

Runs mutmut on selected targets to verify test quality.
Separate from check_all.py due to long execution time (10-60 minutes).

Usage:
    python scripts/mutmut_check.py         # interactive menu
    python scripts/mutmut_check.py 1       # pipeline_steps
    python scripts/mutmut_check.py 2       # chat/manager
    python scripts/mutmut_check.py 5       # full project
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import types
from pathlib import Path
from typing import NoReturn

# ── Constants ────────────────────────────────────────────────────────────────
VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"
_SEP = "─" * 50

TARGETS: dict[str, tuple[str, str]] = {
    "1": ("core/pipeline_steps.py", "src/ai_assistant/core/pipeline_steps.py"),
    "2": ("features/chat/manager.py", "src/ai_assistant/features/chat/manager.py"),
    "3": (
        "adapters/vector_store_*.py",
        "src/ai_assistant/adapters/vector_store_faiss.py "
        "src/ai_assistant/adapters/vector_store_memory.py",
    ),
    "4": ("core/config.py", "src/ai_assistant/core/config.py"),
    "5": ("all", ""),  # uses pyproject.toml paths_to_mutate
}


# ── Auto-activate venv ───────────────────────────────────────────────────────
_venv = Path(__file__).parent.parent / VENV
_venv_py = _venv / PY
if _venv.exists() and _venv_py.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    if "--venv-relaunched" not in sys.argv:
        os.execl(str(_venv_py), str(_venv_py), *sys.argv, "--venv-relaunched")


ROOT = Path(__file__).parent.parent.resolve()


# ── Helpers ──────────────────────────────────────────────────────────────────
def _find_mutmut() -> str | None:
    """Find mutmut executable in PATH or venv."""
    # Check venv first
    venv_mutmut = ROOT / VENV / ("Scripts/mutmut.exe" if os.name == "nt" else "bin/mutmut")
    if venv_mutmut.exists():
        return str(venv_mutmut)
    # Check PATH
    return shutil.which("mutmut")


def _check_mutmut_installed() -> bool:
    """Check if mutmut is available."""
    mutmut_path = _find_mutmut()
    if mutmut_path is None:
        return False
    try:
        result = subprocess.run(
            [mutmut_path, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _run_cmd(cmd: list[str], desc: str) -> bool:
    """Run command with live output streaming."""
    print(f"\n=== {desc} ===\n", flush=True)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["TERM"] = "dumb"
    env["PY_COLORS"] = "0"

    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    if process.stdout:
        for line in iter(process.stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()
        process.stdout.close()

    returncode = process.wait()

    if returncode == 0:
        print(f"\n[OK] {desc}")
        return True
    print(f"\n[FAIL] {desc}")
    return False


def _print_menu() -> None:
    print()
    print(_SEP)
    print("   MUTMUT — Mutation Testing")
    print(_SEP)
    print("  Select target (10-60 minutes per target):")
    print()
    print("    [1] core/pipeline_steps.py     — RAG pipeline (complex logic)")
    print("    [2] features/chat/manager.py   — chat history (edge cases)")
    print("    [3] adapters/vector_store_*.py — vector stores (namespace mgmt)")
    print("    [4] core/config.py             — configuration parsing")
    print("    [5] all                        — full project (slow, hours)")
    print()
    print(_SEP)
    print()


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    def _on_sigint(_signum: int, _frame: types.FrameType | None) -> NoReturn:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)

    try:
        # Check mutmut availability
        if not _check_mutmut_installed():
            print("\n  [ERR] mutmut is not installed.")
            print("  Install it with: pip install mutmut")
            print()
            return 1

        _print_menu()

        # Support CLI argument for non-interactive use
        choice = sys.argv[1] if len(sys.argv) > 1 else None
        if choice is None:
            try:
                choice = input("  Target [1]: ").strip() or "1"
            except EOFError:
                print("\n  ! Input stream closed. Exiting.")
                return 1
            except KeyboardInterrupt:
                print("\n  ! Interrupted by user. Exiting.")
                return 0

        if choice in ("0", "exit", "q", "quit"):
            print("\n  Bye.\n")
            return 0

        if choice not in TARGETS:
            print(f"\n  [ERR] Unknown target: {choice}")
            print(f"  Valid targets: {', '.join(TARGETS.keys())}")
            return 1

        label, mutmut_path = TARGETS[choice]

        print(f"\n  [!] WARNING: This can take 10-60 minutes.")
        print(f"  [!] Press Ctrl+C to abort at any time.\n")

        mutmut_bin = _find_mutmut()
        if mutmut_bin is None:
            print("\n  [ERR] mutmut executable not found.")
            return 1

        cmd = [mutmut_bin, "run"]
        if mutmut_path:
            cmd.extend(["--paths-to-mutate", mutmut_path])

        ok = _run_cmd(cmd, f"MUTMUT RUN ({label})")

        if ok:
            print("\n  Analyzing results...")
            ok &= _run_cmd([mutmut_bin, "results"], "MUTMUT RESULTS")

        print()
        if ok:
            print("  [OK] MUTMUT COMPLETED — all mutations killed")
        else:
            print("  [WARN] MUTMUT FOUND SURVIVING MUTATIONS — review tests")
        print()

        return 0 if ok else 1

    except EOFError:
        print("\n  ! Input stream closed. Exiting.")
        return 1
    except KeyboardInterrupt:
        print("\n  ! Interrupted by user. Exiting.")
        return 0
    except Exception as e:
        print(f"\n  ! Unexpected error: {e}")
        try:
            input("  Press Enter to continue...")
        except EOFError:
            return 1
        return 1


if __name__ == "__main__":
    sys.exit(main())
