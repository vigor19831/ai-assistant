#!/usr/bin/env python3
"""Setup virtual environment and install requirements."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f">> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def main() -> int:
    project_root = Path(__file__).parent.parent.resolve()
    venv_path = project_root / ".venv"

    # Verify Python version
    if sys.version_info < (3, 13):
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(f"WARNING: Python {py_ver} detected.")
        print("This project requires Python 3.13+")
        print("Please install Python 3.13 from https://python.org/downloads/")
        return 1

    if not venv_path.exists():
        print("Creating virtual environment...")
        if run([sys.executable, "-m", "venv", str(venv_path)]) != 0:
            return 1

    if sys.platform == "win32":
        python = venv_path / "Scripts" / "python.exe"
        pip = venv_path / "Scripts" / "pip.exe"
    else:
        python = venv_path / "bin" / "python"
        pip = venv_path / "bin" / "pip"

    print("Upgrading pip...")
    if run([str(python), "-m", "pip", "install", "--upgrade", "pip"]) != 0:
        return 1

    # Determine what to install
    extras = []
    # NOTE: llama.cpp support planned for future; currently use Ollama
    # if "--with-llama" in sys.argv:
    #     extras.append("llama")
    if "--with-faiss" in sys.argv:
        extras.append("faiss")

    # Dev mode: --dev flag OR running from launcher OR no venv existed before
    dev_mode = (
        "--dev" in sys.argv or "LAUNCHER_MODE" in os.environ or not venv_path.exists()
    )

    if dev_mode:
        extras.append("dev")
        print("Dev mode detected — installing dev dependencies")

    # Install everything at once if extras exist, otherwise just core
    if extras:
        extra_str = ",".join(extras)
        print(f"Installing with extras: [{extra_str}]...")
        if run([str(pip), "install", "-e", f"{project_root}[{extra_str}]"]) != 0:
            return 1
    else:
        print("Installing core dependencies...")
        if run([str(pip), "install", "-e", str(project_root)]) != 0:
            return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
