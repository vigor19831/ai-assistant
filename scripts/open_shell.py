#!/usr/bin/env python3
"""Open PowerShell with admin rights + activated .venv."""

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).parent.parent.resolve()
    venv = root / ".venv"

    if os.name != "nt":
        print("This script is Windows-only")
        return 1

    venv_scripts = venv / "Scripts"
    if not venv_scripts.exists():
        print(f"No venv found at {venv}")
        return 1

    new_path = str(venv_scripts) + os.pathsep + os.environ.get("PATH", "")
    new_prompt = "(.venv) " + os.environ.get("PROMPT", "$P$G")

    def _quote_ps(s: str) -> str:
        """Escape single quotes for PowerShell single-quoted string."""
        return s.replace("'", "''")

    # PowerShell command: set policy + activate venv + cd to project
    ps_script = (
        f"Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force; "
        f"$env:PATH = '{_quote_ps(new_path)}'; "
        f"$env:VIRTUAL_ENV = '{_quote_ps(str(venv))}'; "
        f"$env:PROMPT = '{_quote_ps(new_prompt)}'; "
        f"Set-Location '{_quote_ps(str(root))}'; "
        f"Write-Host 'venv activated (admin)' -ForegroundColor Green"
    )

    import ctypes

    # If already admin — just open PowerShell directly
    if ctypes.windll.shell32.IsUserAnAdmin():
        os.system(f'start powershell -NoExit -Command "{ps_script}"')
        return 0

    # Not admin — request elevation via UAC
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,           # hwnd
        "runas",        # operation — triggers UAC dialog
        "powershell.exe",  # file to run
        f'-NoExit -Command "{ps_script}"',  # arguments
        str(root),      # working directory
        1               # SW_SHOWNORMAL
    )
    if ret <= 32:
        print(f"[FAIL] Failed to elevate PowerShell (error {ret})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
