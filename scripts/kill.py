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


def _extract_port(url: str) -> int | None:
    """Extract port from URL like http://host:port/path or http://host/path."""
    if not url:
        return None
    # Handle //host:port/path — skip scheme
    stripped = url.split("//", 1)[-1]  # host:port/path or host/path
    host_part = stripped.split("/", 1)[0]  # host:port or host
    if ":" not in host_part:
        return None
    port_str = host_part.rsplit(":", 1)[-1]  # port (last colon segment)
    try:
        p = int(port_str)
        if 1 <= p <= 65535:
            return p
    except ValueError:
        pass
    return None


def _load_project_ports(root: Path) -> tuple[int, ...]:
    """Read ports from config.yaml. No fallback — if config is broken, we must know."""
    config_path = root / "config.yaml"
    if yaml is None:
        print(f"  [WARN] PyYAML not installed — cannot parse {config_path}")
        return ()
    if not config_path.exists():
        print(f"  [WARN] {config_path} not found — no project ports to check")
        return ()
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        ports: set[int] = set()
        # API server port (root level in config.yaml)
        api_port = data.get("port")
        if isinstance(api_port, int):
            ports.add(api_port)
        # LLM server port from api_base
        llm_config = data.get("llm", {})
        llm_port = _extract_port(llm_config.get("api_base", ""))
        if llm_port is not None:
            ports.add(llm_port)
        # Embedder port from api_base
        embedder_config = data.get("embedder", {})
        emb_port = _extract_port(embedder_config.get("api_base", ""))
        if emb_port is not None:
            ports.add(emb_port)
        # Reranker port from api_base
        reranker_config = data.get("reranker", {})
        rer_port = _extract_port(reranker_config.get("api_base", ""))
        if rer_port is not None:
            ports.add(rer_port)
        if not ports:
            print("  [WARN] No ports found in config — check api_base URLs")
        return tuple(ports)
    except Exception as exc:
        print(f"  [WARN] Failed to read {config_path}: {exc}")
        return ()


def _port_holder_pids(port: int) -> list[int]:
    """Return all PIDs holding *port*, or empty list."""
    pids: list[int] = []
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                if "LISTENING" not in line:
                    continue
                if f":{port}" not in line:
                    continue
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                local_addr = parts[1]
                if not local_addr.endswith(f":{port}"):
                    continue
                try:
                    pid = int(parts[-1])
                    if pid not in pids:
                        pids.append(pid)
                except ValueError:
                    continue
        else:
            # lsof returns one PID per line; fuser returns space-separated PIDs
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
                    for token in result.stdout.strip().split():
                        try:
                            pid = int(token)
                            if pid not in pids:
                                pids.append(pid)
                        except ValueError:
                            continue
    except Exception:
        pass
    return pids


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
            # killall without -q to surface errors (stdout captured anyway)
            subprocess.run(
                ["killall", name],
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
        pids = _port_holder_pids(port)
        if pids:
            print(f"  Port {port} held by PID(s) {pids} — terminating...")
            for pid in pids:
                _kill_pid(pid)
            if not _wait_port_free(port, timeout=2.0):
                print(f"  Port {port} still held — forcing kill...")
                for pid in pids:
                    _kill_pid(pid, force=True)
            if _wait_port_free(port, timeout=1.0):
                print(f"  [OK] Port {port} freed")
            else:
                print(f"  [FAIL] Port {port} STILL held (zombie/D-state?)")
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
