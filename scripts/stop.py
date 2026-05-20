#!/usr/bin/env python3
"""Stop the AI Assistant server and cleanup processes."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def is_running(pid: int) -> bool:
    """Check if a process with given PID exists."""
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            synchronize = 0x00100000
            handle = kernel32.OpenProcess(synchronize, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    pid_file = project_root / "data" / "server.pid"

    if not pid_file.exists():
        print("No PID file found. Server may not be running.")
        return 0

    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        print("Invalid PID file. Removing.")
        pid_file.unlink()
        return 0

    # Check if process is actually alive before trying to kill
    if not is_running(pid):
        print(f"Process {pid} is already gone.")
        pid_file.unlink(missing_ok=True)
        return 0

    print(f"Stopping server (PID {pid})...")

    if os.name == "nt":
        # Windows: taskkill /F /T kills the process tree
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
        )
        # Return code 128 = "process not found" (already dead) — also fine
        if result.returncode == 0 or result.returncode == 128:
            print("Server stopped.")
        else:
            print(f"taskkill warning: {result.stderr.strip()}")
            # If process disappeared during taskkill, that's still success
            if not is_running(pid):
                print("Process is gone anyway.")
            else:
                return 1
    else:
        # Unix: try graceful SIGTERM first, then SIGKILL
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(50):  # wait up to 5 sec
                time.sleep(0.1)
                if not is_running(pid):
                    break
            else:
                print("Graceful shutdown timed out, forcing...")
                try:
                    if hasattr(signal, "SIGKILL"):
                        os.kill(pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                time.sleep(0.3)
            print("Server stopped.")
        except (OSError, ProcessLookupError):
            print("Process already gone.")

    pid_file.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
