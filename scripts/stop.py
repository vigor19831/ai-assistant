#!/usr/bin/env python3
"""Stop the AI Assistant server and cleanup processes."""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


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


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def find_pid_by_port(port: int) -> int | None:
    """Find PID listening on given port (cross-platform)."""
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
        # lsof → ss → fuser
        cmds: list[list[str]] = [
            ["lsof", "-i", f":{port}", "-t"],
            ["ss", "-tlnp", f"sport = :{port}"],
            ["fuser", f"{port}/tcp"],
        ]
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0 or not result.stdout.strip():
                continue
            if cmd[0] == "lsof":
                try:
                    return int(result.stdout.strip().split()[0])
                except ValueError:
                    pass
            elif cmd[0] == "ss":
                for line in result.stdout.splitlines():
                    m = re.search(r'pid=(\d+)', line)
                    if m:
                        return int(m.group(1))
            elif cmd[0] == "fuser":
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
            return int(cfg.get("port", 8000))
        except Exception:
            pass
    return 8000


def _get_api_ports(project_root: Path) -> list[int]:
    """Return local llama-server ports from config (for stray cleanup)."""
    config_path = project_root / "config.yaml"
    ports: list[int] = []
    if not config_path.exists():
        return ports
    try:
        import yaml
        from urllib.parse import urlparse
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        for key in ("llm", "embedder"):
            base = cfg.get(key, {}).get("api_base", "")
            if base.startswith(("http://127.0.0.1", "http://localhost")):
                p = urlparse(base.rstrip("/")).port
                if p:
                    ports.append(p)
    except Exception:
        pass
    return ports


def _kill_graceful(pid: int, name: str = "process", timeout: float = 5.0) -> bool:
    """SIGTERM → wait → SIGKILL. Returns True if process is gone."""
    if not is_running(pid):
        print(f"  {name} (PID {pid}) already gone.")
        return True

    print(f"  Stopping {name} (PID {pid})...")

    if os.name == "nt":
        # Windows: taskkill /F /T сразу (graceful невозможен без WMI)
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
        )
        time.sleep(0.5)
        return not is_running(pid)

    # Unix: graceful SIGTERM
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return True

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.1)
        if not is_running(pid):
            print(f"  {name} stopped gracefully.")
            return True

    # Force kill
    print(f"  {name} forced (SIGKILL)...")
    try:
        if hasattr(signal, "SIGKILL"):
            os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    time.sleep(0.3)
    return not is_running(pid)


def _kill_by_name(name: str) -> None:
    """Kill by executable name (last resort)."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/IM", name],
            capture_output=True,
        )
    else:
        subprocess.run(
            ["pkill", "-9", "-f", name],
            capture_output=True,
        )


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    uvicorn_pid_file = data_dir / "uvicorn.pid"
    legacy_pid_file = data_dir / "server.pid"
    llama_pid_file = data_dir / "llama-server.pid"
    port = _get_config_port(project_root)
    api_ports = _get_api_ports(project_root)

    print("[stop] Stopping AI Assistant...")

    # ── 1. Main uvicorn server ──
    uvicorn_stopped = False
    pid: int | None = None
    used_pid_file: Path | None = None

    # Prefer new uvicorn.pid, fallback to legacy server.pid
    for pid_file in (uvicorn_pid_file, legacy_pid_file):
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                used_pid_file = pid_file
                break
            except ValueError:
                print(f"  Invalid PID file {pid_file.name}, removing.")
                pid_file.unlink()

    if pid is not None and is_running(pid):
        uvicorn_stopped = _kill_graceful(pid, "uvicorn")
    elif pid is not None:
        print(f"  PID {pid} from {used_pid_file.name} already dead.")

    # Fallback: find by port
    if not uvicorn_stopped:
        fallback_pid = find_pid_by_port(port)
        if fallback_pid:
            print(f"  Found server on port {port} (PID {fallback_pid})")
            uvicorn_stopped = _kill_graceful(fallback_pid, "uvicorn")

    # ── 2. llama-server instances ──
    llama_pids: list[int] = []
    if llama_pid_file.exists():
        try:
            text = llama_pid_file.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.strip():
                    lpid = int(line.strip())
                    if is_running(lpid):
                        llama_pids.append(lpid)
        except ValueError:
            print("  Invalid llama-server PID file, removing.")
            llama_pid_file.unlink()

    for lpid in llama_pids:
        _kill_graceful(lpid, "llama-server")

    # Catch stray llama-servers on API ports
    for api_port in api_ports:
        if is_port_in_use(api_port):
            stray = find_pid_by_port(api_port)
            if stray and stray not in llama_pids:
                print(f"  Stray server on API port {api_port} (PID {stray})")
                _kill_graceful(stray, "llama-server")

    # Last resort: by process name
    print("  Cleaning up remaining llama-server processes...")
    _kill_by_name("llama-server.exe" if os.name == "nt" else "llama-server")

    # ── 3. Verify ports are free ──
    time.sleep(0.3)
    all_ports = [port] + api_ports
    for p in all_ports:
        if is_port_in_use(p):
            print(f"  WARNING: port {p} still in use!")
        else:
            print(f"  Port {p} is free.")

    # ── 4. Cleanup PID files ──
    for pid_file in data_dir.glob("*.pid"):
        pid_file.unlink(missing_ok=True)

    print("[stop] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
