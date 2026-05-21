#!/usr/bin/env python3
"""Setup virtual environment and install requirements."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f">> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def ask(question: str, default: bool = True) -> bool:
    """Ask yes/no question in interactive terminal."""
    if not sys.stdin.isatty():
        return default
    hint = "Y/n" if default else "y/N"
    try:
        ans = input(f"{question} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return default
    if not ans:
        return default
    return ans in ("y", "yes")


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup virtual environment")
    parser.add_argument("--dev", action="store_true", help="Install dev dependencies")
    parser.add_argument("--no-dev", action="store_true", help="Skip dev dependencies")
    parser.add_argument("--with-faiss", action="store_true", help="Install FAISS")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent.resolve()
    venv_path = project_root / ".venv"

    # Verify Python version
    if sys.version_info < (3, 13):
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        print(f"WARNING: Python {py_ver} detected.")
        print("This project requires Python 3.13+")
        print("Please install Python 3.13 from https://python.org/downloads/")
        return 1

    venv_created = False
    if not venv_path.exists():
        print("Creating virtual environment...")
        if run([sys.executable, "-m", "venv", str(venv_path)]) != 0:
            return 1
        venv_created = True

    if sys.platform == "win32":
        python = venv_path / "Scripts" / "python.exe"
        pip = venv_path / "Scripts" / "pip.exe"
    else:
        python = venv_path / "bin" / "python"
        pip = venv_path / "bin" / "pip"

    print("Upgrading pip...")
    if run([str(python), "-m", "pip", "install", "--upgrade", "pip"]) != 0:
        return 1

    # Determine extras
    extras = []
    if args.with_faiss:
        extras.append("faiss")

    # Determine dev mode
    if args.dev:
        install_dev = True
    elif args.no_dev:
        install_dev = False
    elif venv_created:
        # Fresh venv: default to dev, but ask if interactive
        install_dev = ask("Install dev dependencies (pytest, ruff, mypy, etc.)?", default=True)
    else:
        # Existing venv: ask, default no
        install_dev = ask("Install dev dependencies (pytest, ruff, mypy, etc.)?", default=False)

    if install_dev:
        extras.append("dev")
        print("Including dev dependencies")

    # Install
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
