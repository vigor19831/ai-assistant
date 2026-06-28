#!/usr/bin/env python3
"""One-click setup for first-time users.

Run from project root:
    python scripts/setup.py        (Windows)
    python3 scripts/setup.py       (macOS / Linux)

Creates .venv, installs dependencies, copies config, creates data folders.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

MIN_PYTHON = (3, 11)
VENV_DIR = ".venv"
PYTHON_DOWNLOAD_URL = "https://www.python.org/downloads/"


def _error(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"[INFO] {msg}")


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _check_python() -> str:
    """Verify Python version and return executable path."""
    version = sys.version_info[:2]
    if version < MIN_PYTHON:
        _error(
            f"Python {version[0]}.{version[1]} found, "
            f"but {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required."
        )
        _info(f"Please install Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ from:")
        _info(f"  {PYTHON_DOWNLOAD_URL}")
        _info("")
        _info("Windows: check 'Add Python to PATH' during installation.")
        _info("macOS:   use the installer from python.org or 'brew install python@3.11'")
        _info("Linux:   use your package manager, e.g. 'sudo apt install python3.11'")
        _info("")
        _info("Opening download page in your browser...")
        try:
            webbrowser.open(PYTHON_DOWNLOAD_URL)
        except Exception:
            pass
        sys.exit(1)
    return sys.executable


def _get_venv_python(root: Path) -> str:
    """Return path to python inside .venv."""
    if os.name == "nt":
        return str(root / VENV_DIR / "Scripts" / "python.exe")
    return str(root / VENV_DIR / "bin" / "python")


def _create_venv(root: Path, py: str) -> Path:
    """Create virtual environment in .venv/."""
    venv_path = root / VENV_DIR

    if venv_path.exists():
        venv_py = _get_venv_python(root)
        if Path(venv_py).exists():
            _info("Virtual environment already exists.")
            return venv_path
        _info("Virtual environment path is invalid (folder moved?). Recreating...")
        shutil.rmtree(venv_path)

    _info("Creating virtual environment...")
    subprocess.run([py, "-m", "venv", str(venv_path)], check=True)
    _ok(f"Virtual environment created at {venv_path}")
    return venv_path


def _install_deps(venv_py: str, root: Path) -> None:
    """Install project dependencies."""
    _info("Installing dependencies (this may take a few minutes)...")
    subprocess.run(
        [venv_py, "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [venv_py, "-m", "pip", "install", "."],
        cwd=root,
        check=True,
    )
    _ok("Dependencies installed")


def _copy_env(root: Path) -> None:
    """Copy .env.example to .env if not present."""
    example = root / ".env.example"
    target = root / ".env"
    if target.exists():
        _info(".env already exists -- skipping")
        return
    if not example.exists():
        _error(".env.example not found -- cannot create .env")
        return
    shutil.copy2(example, target)
    _ok(".env created from .env.example")


def _create_dirs(root: Path) -> None:
    """Create required data directories."""
    dirs = [
        root / "data",
        root / "data" / "tokenizers",
        root / "data" / "indices",
        root / "sources",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    _ok("Data directories created")


def _print_next_steps(root: Path) -> None:
    """Print instructions to start the server."""
    if os.name == "nt":
        venv_python = root / VENV_DIR / "Scripts" / "python.exe"
        activate_cmd = str(root / VENV_DIR / "Scripts" / "activate.bat")
    else:
        venv_python = root / VENV_DIR / "bin" / "python"
        activate_cmd = f"source {root / VENV_DIR / 'bin' / 'activate'}"

    print()
    print("=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print()
    print("Your project is ready. Next steps:")
    print()
    print("1. Activate the virtual environment:")
    print(f"   {activate_cmd}")
    print()
    print("2. Edit .env with your API keys (or leave empty for local servers)")
    print()
    print("3. Edit config.yaml with your settings (LLM API endpoint, etc.)")
    print()
    print("4. Start the server:")
    print(f"   {venv_python} -m uvicorn ai_assistant.main:create_app --reload")
    print()
    print("   Then open http://localhost:8000 in your browser.")
    print()
    print("   Or use the script runner:")
    print(f"   {venv_python} run_scripts.py")
    print()
    print("=" * 60)


def main() -> int:
    root = Path(__file__).parent.parent.resolve()
    os.chdir(root)

    print("=" * 60)
    print("AI Assistant -- Setup")
    print("=" * 60)
    print()

    py = _check_python()
    _info(f"Using Python: {py}")

    _create_venv(root, py)
    venv_py = _get_venv_python(root)
    _install_deps(venv_py, root)
    _copy_env(root)
    _create_dirs(root)
    _print_next_steps(root)

    print()
    input("Press Enter to exit...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
