#!/usr/bin/env python3
"""AI Assistant — emergency kill switch.

Kills ALL llama-server processes, uvicorn, and anything holding project ports.
Cross-platform: Windows, Linux, macOS.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Ports used by the project (must match config.yaml defaults)
_PROJECT_PORTS = (8080, 8081, 8000)

# Process names to kill
_KILL_NAMES = ("llama-server", "llama-server.exe", "uvicorn")


def _port_holder_pid(port: int) -> int | None:
    """Return PID of process holding *port*, or None."""
    try:
        if os.name == "nt":
            # netstat -ano | findstr :PORT
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and ("LISTENING" in line or "ESTABLISHED" in line):
                    parts = line.strip().split()
                    if parts:
                        try:
                            return int(parts[-1])
                        except ValueError:
                            continue
        else:
            # lsof -ti:PORT or ss -ltnp
            for cmd in (
                ["lsof", "-ti", f":{port}"],
                ["fuser", f"{port}/tcp"],
            ):
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        return int(result.stdout.strip().split()[0])
                    except (ValueError, IndexError):
                        continue
    except Exception:
        pass
    return None


def _kill_pid(pid: int, force: bool = False) -> bool:
    """Kill process by PID. Returns True if signal sent."""
    try:
        if os.name == "nt":
            args = ["taskkill", "/F", "/PID", str(pid)] if force else ["taskkill", "/PID", str(pid)]
            subprocess.run(args, capture_output=True, check=False)
        else:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _kill_by_name(name: str) -> int:
    """Kill all processes matching *name*. Returns count killed."""
    killed = 0
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/F", "/IM", name],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                killed += 1
        else:
            # Try pkill first
            result = subprocess.run(
                ["pkill", "-f", name],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                killed += 1
            # Also try killall
            subprocess.run(
                ["killall", "-q", name],
                capture_output=True,
                check=False,
            )
    except FileNotFoundError:
        pass
    return killed


def _wait_port_free(port: int, timeout: float = 3.0) -> bool:
    """Wait until port is free."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.2)
    return False


def main() -> int:
    print("=" * 50)
    print("  AI Assistant — Emergency Kill Switch")
    print("=" * 50)

    # 1. Kill by process names
    print("\n[1/3] Killing by process name...")
    for name in _KILL_NAMES:
        killed = _kill_by_name(name)
        if killed:
            print(f"  ✓ Sent kill to: {name}")
        else:
            print(f"  - Not found: {name}")

    # 2. Kill by port holders
    print("\n[2/3] Killing port holders...")
    for port in _PROJECT_PORTS:
        pid = _port_holder_pid(port)
        if pid is not None:
            print(f"  Port {port} held by PID {pid} — terminating...")
            _kill_pid(pid)
            if not _wait_port_free(port, timeout=2.0):
                print(f"  Port {port} still held — forcing kill...")
                _kill_pid(pid, force=True)
            if _wait_port_free(port, timeout=1.0):
                print(f"  ✓ Port {port} freed")
            else:
                print(f"  ✗ Port {port} STILL held (permission denied?)")
        else:
            print(f"  ✓ Port {port} already free")

    # 3. Clean PID file
    print("\n[3/3] Cleaning PID files...")
    root = Path(__file__).parent.resolve()
    pid_file = root / "data" / "uvicorn.pid"
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)
        print(f"  ✓ Removed {pid_file}")

    print("\n" + "=" * 50)
    print("  Done.")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
