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

    def _quote_ps(s: str) -> str:
        """Escape single quotes for PowerShell single-quoted string."""
        return s.replace("'", "''")

    # PowerShell command: set policy + activate venv + cd to project
    ps_script = (
        f"Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force; "
        f"$env:PATH = '{_quote_ps(new_path)}'; "
        f"$env:VIRTUAL_ENV = '{_quote_ps(str(venv))}'; "
        f"Set-Location '{_quote_ps(str(root))}'; "
        f"Write-Host 'venv activated (admin)' -ForegroundColor Green"
    )

    import ctypes

    # windll is win32-only (typeshed and runtime); the os.name guard
    # at the top of main() already returned elsewhere. 3-arg getattr
    # keeps mypy green on both platforms without ignores; the None
    # check below is fail-loud, not a real path.
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        print("[FAIL] ctypes.windll unavailable (Windows only)")
        return 1

    # If already admin — just open PowerShell directly
    if windll.shell32.IsUserAnAdmin():
        code = os.system(f'start powershell -NoExit -Command "{ps_script}"')
        if code != 0:
            print(f"[FAIL] start failed (exit {code})")
            return 1
        return 0

    # Not admin — request elevation via UAC
    ret = windll.shell32.ShellExecuteW(
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
