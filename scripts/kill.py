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

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

# Process names to kill
_KILL_NAMES = ("llama-server", "llama-server.exe", "uvicorn")


def _load_project_ports(root: Path) -> tuple[int, ...]:
    """Read ports from config.yaml, fallback to defaults."""
    config_path = root / "config.yaml"
    defaults = (8080, 8081, 8000)
    if yaml is None or not config_path.exists():
        return defaults
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        ports: set[int] = set()
        # API server port (root level in config.yaml)
        api_port = data.get("port")
        if isinstance(api_port, int):
            ports.add(api_port)
        # LLM server port(s) from api_base
        llm_config = data.get("llm", {})
        api_base = llm_config.get("api_base", "")
        for part in api_base.split(":"):
            try:
                p = int(part.rstrip("/").split("/")[-1])
                if 1 <= p <= 65535:
                    ports.add(p)
            except ValueError:
                continue
        return tuple(ports) if ports else defaults
    except Exception:
        return defaults


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
    root = Path(__file__).resolve().parent.parent
    project_ports = _load_project_ports(root)

    print("=" * 50)
    print("  AI Assistant — Emergency Kill Switch")
    print("=" * 50)

    # 1. Kill by process names
    print("\n[1/3] Killing by process name...")
    for name in _KILL_NAMES:
        killed = _kill_by_name(name)
        if killed:
            print(f"  [OK] Sent kill to: {name}")
        else:
            print(f"  [SKIP] Not found: {name}")

    # 2. Kill by port holders
    print("\n[2/3] Killing port holders...")
    for port in project_ports:
        pid = _port_holder_pid(port)
        if pid is not None:
            print(f"  Port {port} held by PID {pid} — terminating...")
            _kill_pid(pid)
            if not _wait_port_free(port, timeout=2.0):
                print(f"  Port {port} still held — forcing kill...")
                _kill_pid(pid, force=True)
            if _wait_port_free(port, timeout=1.0):
                print(f"  [OK] Port {port} freed")
            else:
                print(f"  [FAIL] Port {port} STILL held (permission denied?)")
        else:
            print(f"  [OK] Port {port} already free")

    # 3. Clean PID file
    print("\n[3/3] Cleaning PID files...")
    pid_file = root / "data" / "uvicorn.pid"
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)
        print(f"  [OK] Removed {pid_file}")

    print("\n" + "=" * 50)
    print("  Done.")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
