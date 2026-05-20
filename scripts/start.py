#!/usr/bin/env python3
"""Start server — uvicorn + auto-start Ollama if bundled."""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_running(pid: int) -> bool:
    """Cross-platform check if a process is alive. Never blocks."""
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        synchronize = 0x00100000
        wait_timeout = 0x00000102

        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        result = kernel32.WaitForSingleObject(handle, 0)
        kernel32.CloseHandle(handle)
        return result == wait_timeout

    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def get_config() -> dict:
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config.yaml"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_python_exe(project_root: Path | None = None) -> str:
    if project_root is None:
        project_root = Path(__file__).parent.parent
    venv = project_root / ".venv"
    if sys.platform == "win32":
        candidate = venv / "Scripts" / "python.exe"
    else:
        candidate = venv / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def _get_ollama_platform_suffix() -> str:
    """Return platform suffix for bundled Ollama binary."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    arch_map = {
        "amd64": "amd64",
        "x86_64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    arch = arch_map.get(machine, machine)

    if system == "windows":
        return f"windows-{arch}.exe"
    elif system == "darwin":
        return f"darwin-{arch}"
    elif system == "linux":
        return f"linux-{arch}"
    else:
        return f"{system}-{arch}"


def _find_ollama_exe(project_root: Path, config: dict) -> Path | None:
    """Find Ollama: config -> vendor/ (platform-specific) -> vendor/ollama.exe -> vendor/ollama/ -> PATH."""
    # 1. Explicit path from config.yaml
    cfg_path = config.get("ollama", {}).get("exe_path")
    if cfg_path:
        p = Path(cfg_path).expanduser()
        if p.exists():
            return p.resolve()

    # 2. Bundled: vendor/ollama-{platform}
    suffix = _get_ollama_platform_suffix()
    platform_binary = project_root / "vendor" / f"ollama-{suffix}"
    if platform_binary.exists():
        return platform_binary.resolve()

    # 3. Bundled: vendor/ollama.exe (Windows portable) or vendor/ollama
    for name in ("ollama.exe", "ollama"):
        flat = project_root / "vendor" / name
        if flat.exists():
            return flat.resolve()

    # 4. Bundled: vendor/ollama/ollama.exe or vendor/ollama/ollama
    for name in ("ollama.exe", "ollama"):
        nested = project_root / "vendor" / "ollama" / name
        if nested.exists():
            return nested.resolve()

    # 5. System PATH
    for path_dir in os.getenv("PATH", "").split(os.pathsep):
        for name in ("ollama.exe", "ollama"):
            p = Path(path_dir) / name
            if p.exists():
                return p.resolve()
    return None


def _ensure_ollama_running(project_root: Path, config: dict) -> None:
    """Start Ollama if not running and path found."""
    if is_port_in_use(11434):
        print("[start] Ollama already running on :11434")
        return

    ollama = _find_ollama_exe(project_root, config)
    if ollama is None:
        print("[start] WARNING: Ollama not found")
        print("[start] Set ollama.exe_path in config.yaml or install Ollama")
        print(f"[start] Expected: vendor/ollama-{_get_ollama_platform_suffix()}")
        return

    # ── Portable Ollama env — blobs go to vendor/ollama/models, not user profile ──
    env = os.environ.copy()
    ollama_home = project_root / "vendor" / "ollama"
    ollama_home.mkdir(parents=True, exist_ok=True)
    env["OLLAMA_MODELS"] = str(ollama_home / "models")
    env["OLLAMA_HOST"] = "127.0.0.1:11434"

    print(f"[start] Starting Ollama: {ollama}")
    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen([str(ollama), "serve"], **kwargs)

    for _ in range(30):
        time.sleep(0.5)
        if is_port_in_use(11434):
            print("[start] Ollama ready")
            return
    print("[start] WARNING: Ollama did not respond in 15s")


def main() -> int:
    project_root = Path(__file__).parent.parent.resolve()
    (project_root / "data").mkdir(parents=True, exist_ok=True)

    config = get_config()
    port = config.get("port", 8000)
    host = config.get("host", "127.0.0.1")

    _ensure_ollama_running(project_root, config)

    if is_port_in_use(port):
        print(f"WARNING: Port {port} is already in use!")
        return 1

    pid_file = project_root / "data" / "server.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    python = get_python_exe(project_root)

    return subprocess.run(
        [
            python,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=project_root,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
