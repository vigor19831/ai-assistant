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


def find_pid_by_port(port: int) -> int | None:
    """Find PID listening on given port (fallback)."""
    if os.name == "nt":
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, shell=False
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        continue
    else:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            try:
                return int(result.stdout.strip().split()[0])
            except ValueError:
                pass
    return None


def _get_config_port(project_root: Path) -> int:
    config_path = project_root / "config.yaml"
    if config_path.exists():
        try:
            import yaml

            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return cfg.get("port", 8000)
        except Exception:
            pass
    return 8000


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent.parent
    pid_file = project_root / "data" / "server.pid"
    port = _get_config_port(project_root)

    pid: int | None = None

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            print("Invalid PID file. Removing.")
            pid_file.unlink()
            pid = None

    # Check if process from PID file is actually alive
    if pid is not None and not is_running(pid):
        print(f"Process {pid} from PID file is already gone.")
        pid = None

    # Fallback: try to find by port if no valid PID
    if pid is None:
        port_pid = find_pid_by_port(port)
        if port_pid:
            print(f"Found process {port_pid} on port {port}, using it.")
            pid = port_pid
        else:
            print(f"No PID file and no process found on port {port}.")
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
        if result.returncode not in (0, 128):
            print(f"taskkill warning: {result.stderr.strip()}")
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
        except (OSError, ProcessLookupError):
            print("Process already gone.")

    # Verify the process is actually gone
    time.sleep(0.5)
    if is_running(pid):
        print(f"WARNING: Process {pid} is still running!")
        return 1

    print("Server stopped.")
    pid_file.unlink(missing_ok=True)

    # Kill llama-server by PID first (from llama-server.pid), fallback by name
    llama_pid_file = project_root / "data" / "llama-server.pid"
    if llama_pid_file.exists():
        try:
            for line in llama_pid_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                lpid = int(line.strip())
                if is_running(lpid):
                    print(f"Stopping llama-server (PID {lpid})...")
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(lpid)],
                            capture_output=True,
                        )
                    else:
                        try:
                            os.kill(lpid, signal.SIGTERM)
                            time.sleep(0.5)
                            if is_running(lpid):
                                os.kill(lpid, signal.SIGKILL)
                        except Exception:
                            pass
        except Exception:
            pass
        llama_pid_file.unlink(missing_ok=True)

    # Fallback: kill any remaining llama-server processes by executable name
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/IM", "llama-server.exe"],
            capture_output=True,
        )
    else:
        subprocess.run(
            ["pkill", "-9", "-f", "llama-server"],
            capture_output=True,
        )

    # Clean up all PID files
    for extra_pid in (project_root / "data").glob("*.pid"):
        extra_pid.unlink(missing_ok=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
