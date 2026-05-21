#!/usr/bin/env python3
"""Start server — auto-launch llama-server + uvicorn + health checks."""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

import httpx
import yaml

# ── Platform-specific executable name ──
LLAMA_SERVER_EXE = "llama-server.exe" if os.name == "nt" else "llama-server"

# ── Process registry for cleanup ──
_spawned_procs: list[subprocess.Popen[Any]] = []


def _cleanup_servers() -> None:
    """Terminate all spawned llama-server processes on exit."""
    for proc in _spawned_procs:
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                    time.sleep(1.0)
                    if proc.poll() is None:
                        proc.kill()
                else:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception:
                pass


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def wait_for_port(port: int, timeout: float = 30.0, host: str = "127.0.0.1") -> bool:
    """Wait for a port to become accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_port_in_use(port):
            time.sleep(0.2)
            continue
        try:
            resp = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
            if resp.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _get_port(api_base: str) -> int:
    """Extract port from API base URL (e.g. http://127.0.0.1:8080/v1 → 8080)."""
    parsed = urlparse(api_base.rstrip("/"))
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def get_config() -> dict[str, Any]:
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


def _resolve_model_path(model_name: str) -> Path | None:
    """Resolve model name to actual .gguf file path."""
    project_root = Path(__file__).parent.parent
    search_dirs = [
        project_root / "vendor" / "models",
        project_root / "models",
    ]

    for directory in search_dirs:
        if not directory.exists():
            continue
        for ext in [".gguf", ".GGUF"]:
            exact = directory / f"{model_name}{ext}"
            if exact.exists():
                return exact
        for file in directory.iterdir():
            if file.suffix.lower() == ".gguf" and model_name.lower() in file.name.lower():
                return file
    return None


def _find_llama_server_exe() -> Path | None:
    """Find llama-server executable in known locations."""
    project_root = Path(__file__).parent.parent

    search_paths = [
        project_root / "vendor" / "llama" / LLAMA_SERVER_EXE,
        project_root / "vendor" / "llama" / "build" / "bin" / LLAMA_SERVER_EXE,
        project_root / "vendor" / "llama.cpp" / "build" / "bin" / LLAMA_SERVER_EXE,
        project_root / "vendor" / "llama.cpp" / LLAMA_SERVER_EXE,
    ]


    path_found = shutil.which(LLAMA_SERVER_EXE)
    if path_found:
        search_paths.insert(0, Path(path_found))

    for candidate in search_paths:
        if candidate.exists():
            return candidate
    return None


def _start_llama_server(
    model_path: Path,
    port: int,
    ngl: int = 0,
    ctx_size: int = 4096,
    embeddings: bool = False,
    pooling: str | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.Popen[Any] | None:
    """Start llama-server as a background process."""

    if is_port_in_use(port):
        print(f"[start] Port {port} already in use — assuming server is running")
        return None

    exe_path = _find_llama_server_exe()
    if exe_path is None:
        print(f"[start] ERROR: {LLAMA_SERVER_EXE} not found. Checked:")
        project_root = Path(__file__).parent.parent
        checked = [
            project_root / "vendor" / "llama" / LLAMA_SERVER_EXE,
            project_root / "vendor" / "llama" / "build" / "bin" / LLAMA_SERVER_EXE,
            project_root / "vendor" / "llama.cpp" / "build" / "bin" / LLAMA_SERVER_EXE,
        ]
        for p in checked:
            print(f"    {p}")
        print(f"[start] Please place {LLAMA_SERVER_EXE} in vendor/llama/ or add to PATH")
        return None

    cmd = [
        str(exe_path),
        "-m",
        str(model_path),
        "--port",
        str(port),
        "-ngl",
        str(ngl),
        "-c",
        str(ctx_size),
    ]

    if embeddings:
        cmd.append("--embeddings")
        if pooling:
            cmd.extend(["--pooling", pooling])

    if extra_args:
        cmd.extend(extra_args)

    print(f"[start] Starting {LLAMA_SERVER_EXE} on port {port}...")
    print(f"[start] Model: {model_path.name}")
    print(f"[start] Command: {' '.join(cmd)}")

    kwargs: dict[str, Any] = {
        "cwd": str(exe_path.parent),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }

    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        proc = subprocess.Popen(cmd, **kwargs)
        _spawned_procs.append(proc)

        if wait_for_port(port, timeout=60.0):
            print(f"[start] {LLAMA_SERVER_EXE} ready on port {port} (PID {proc.pid})")
            return proc
        else:
            print(f"[start] WARNING: {LLAMA_SERVER_EXE} on port {port} did not respond in time")
            try:
                proc.kill()
            except Exception:
                pass
            return None
    except Exception as e:
        print(f"[start] ERROR starting {LLAMA_SERVER_EXE}: {e}")
        return None


def _start_embedder_server(config: dict[str, Any]) -> subprocess.Popen[Any] | None:
    """Start embedding model server if configured and not already running."""
    embedder = config.get("embedder", {})
    api_base = embedder.get("api_base", "")

    if not api_base.startswith(("http://127.0.0.1", "http://localhost")):
        return None

    port = _get_port(api_base)
    model_name = embedder.get("model", "")
    ngl = embedder.get("n_gpu_layers", 0)

    model_path = _resolve_model_path(model_name)
    if model_path is None:
        print(f"[start] WARNING: Embedding model '{model_name}' not found in vendor/models/")
        return None

    return _start_llama_server(
        model_path=model_path,
        port=port,
        ngl=ngl,
        ctx_size=512,
        embeddings=True,
        pooling="mean",
    )


def _start_llm_server(config: dict[str, Any]) -> subprocess.Popen[Any] | None:
    """Start main LLM server if configured and not already running."""
    llm = config.get("llm", {})
    api_base = llm.get("api_base", "")

    if not api_base.startswith(("http://127.0.0.1", "http://localhost")):
        return None

    port = _get_port(api_base)
    model_name = llm.get("model", "")
    ngl = llm.get("n_gpu_layers", 99)
    ctx_size = llm.get("server_context_size", 4096)

    model_path = _resolve_model_path(model_name)
    if model_path is None:
        print(f"[start] WARNING: LLM model '{model_name}' not found in vendor/models/")
        return None

    return _start_llama_server(
        model_path=model_path,
        port=port,
        ngl=ngl,
        ctx_size=ctx_size,
    )


def _check_llm_server(config: dict[str, Any]) -> bool:
    llm = config.get("llm", {})
    api_base = os.getenv(
        "AI_LLM_API_BASE",
        llm.get("api_base", "http://127.0.0.1:8080/v1"),
    ).rstrip("/")
    try:
        resp = httpx.get(f"{api_base}/models", timeout=5.0)
        return resp.status_code < 500
    except Exception:
        return False


def _check_embedder_server(config: dict[str, Any]) -> bool:
    embedder = config.get("embedder", {})
    api_base = embedder.get("api_base", "http://127.0.0.1:8081/v1").rstrip("/")
    try:
        resp = httpx.get(f"{api_base}/models", timeout=5.0)
        return resp.status_code < 500
    except Exception:
        return False


def main() -> int:
    atexit.register(_cleanup_servers)

    project_root = Path(__file__).parent.parent.resolve()
    (project_root / "data").mkdir(parents=True, exist_ok=True)

    config = get_config()
    port = config.get("port", 8000)
    host = config.get("host", "127.0.0.1")

    # ── Auto-start LLM server ──
    llm_ok = _check_llm_server(config)
    if not llm_ok:
        print("[start] LLM server not detected — attempting auto-start...")
        _start_llm_server(config)
        llm_ok = _check_llm_server(config)

    if not llm_ok:
        print("[start] WARNING: LLM server unavailable. Framework will use mock/fallback.")
        print(f"[start] Start manually: {LLAMA_SERVER_EXE} -m model.gguf --port 8080")

    # ── Auto-start embedder server ──
    emb_ok = _check_embedder_server(config)
    if not emb_ok:
        print("[start] Embedder server not detected — attempting auto-start...")
        _start_embedder_server(config)
        emb_ok = _check_embedder_server(config)

    if not emb_ok:
        print("[start] WARNING: Embedder server unavailable. RAG features disabled.")

    # ── Start uvicorn ──
    if is_port_in_use(port):
        print(f"WARNING: Port {port} is already in use!")
        return 1

    python = get_python_exe(project_root)

    print(f"[start] Starting uvicorn on {host}:{port}")
    print("[start] Press Ctrl+C to stop all servers")

    try:
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
    except KeyboardInterrupt:
        print("\n[start] Shutting down...")
        _cleanup_servers()
        return 0


if __name__ == "__main__":
    sys.exit(main())
