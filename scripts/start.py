#!/usr/bin/env python3
"""Start server — auto-launch llama-server + uvicorn (background, no console window)."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import httpx
except Exception as e:
    print(f"[start] httpx import FAILED: {e}", flush=True)
    sys.exit(1)

try:
    import yaml
except Exception as e:
    print(f"[start] yaml import FAILED: {e}", flush=True)
    sys.exit(1)

LLAMA_SERVER_EXE = "llama-server.exe" if os.name == "nt" else "llama-server"
_spawned_procs: list[subprocess.Popen[Any]] = []


def _kill_process_tree(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            import psutil
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
    except Exception:
        pass


def _cleanup_servers() -> None:
    project_root = Path(__file__).parent.parent
    pid_file = project_root / "data" / "llama-server.pid"
    if pid_file.exists():
        try:
            for line in pid_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    _kill_process_tree(int(line.strip()))
        except Exception:
            pass
        pid_file.unlink(missing_ok=True)
    for proc in list(_spawned_procs):
        try:
            if proc.poll() is None:
                _kill_process_tree(proc.pid)
        except Exception:
            pass


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def wait_for_port(port: int, timeout: float = 30.0, host: str = "127.0.0.1") -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_port_in_use(port):
            time.sleep(0.2)
            continue
        try:
            resp = httpx.get(f"http://{host}:{port}/models", timeout=2.0)
            if resp.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _get_port(api_base: str) -> int:
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
    project_root = Path(__file__).parent.parent
    for directory in [project_root / "vendor" / "models", project_root / "models"]:
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


def _prepare_subprocess_kwargs(port: int | None = None, detached: bool = False) -> dict[str, Any]:
    """Return cross-platform kwargs to hide console and isolate process group.

    stdout/stderr go to log files — llama-server.exe is a console app
    and dies on Windows if both console is hidden AND pipes are DEVNULL.
    """
    project_root = Path(__file__).parent.parent
    log_dir = project_root / "data"          # ← было "logs", стало "data"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Open log files for append (one per port, or generic if no port)
    suffix = f"_{port}" if port else ""
    out_log = open(log_dir / f"llama_server{suffix}_out.log", "a", encoding="utf-8")
    err_log = open(log_dir / f"llama_server{suffix}_err.log", "a", encoding="utf-8")
    ...

    kwargs: dict[str, Any] = {
        "stdout": out_log,
        "stderr": err_log,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,  # ← не наследовать дескрипторы лаунчера
    }
    if os.name == "nt":
        if detached:
            # Полное отцепление от консоли: сервер НЕ умрёт при закрытии лаунчера
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            )
        else:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _start_llama_server(
    model_path: Path,
    port: int,
    ngl: int = 0,
    ctx_size: int = 4096,
    embeddings: bool = False,
    pooling: str | None = None,
    detached: bool = False,
) -> subprocess.Popen[Any] | None:
    project_root = Path(__file__).parent.parent
    if is_port_in_use(port):
        print(f"[start] Port {port} already in use — assuming server is running")
        return None

    exe_path = _find_llama_server_exe()
    if exe_path is None:
        print(f"[start] ERROR: {LLAMA_SERVER_EXE} not found.")
        return None

    cmd = [
        str(exe_path), "-m", str(model_path),
        "--host", "127.0.0.1", "--port", str(port),
        "-ngl", str(ngl), "-c", str(ctx_size),
    ]
    if embeddings:
        cmd.append("--embedding")
        if pooling:
            cmd.extend(["--pooling", pooling])

    kwargs = _prepare_subprocess_kwargs(port=port, detached=detached)
    kwargs["cwd"] = str(project_root)

    try:
        proc = subprocess.Popen(cmd, **kwargs)
        _spawned_procs.append(proc)
        pid_file = project_root / "data" / "llama-server.pid"
        existing = []
        if pid_file.exists():
            existing = [line for line in pid_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        existing.append(str(proc.pid))
        pid_file.write_text("\n".join(existing) + "\n", encoding="utf-8")

        if wait_for_port(port, timeout=60.0):
            print(f"[start] {LLAMA_SERVER_EXE} ready on port {port} (PID {proc.pid})")
            return proc
        else:
            print(f"[start] WARNING: {LLAMA_SERVER_EXE} did not respond in time")
            _kill_process_tree(proc.pid)
            return None
    except Exception as e:
        print(f"[start] ERROR starting {LLAMA_SERVER_EXE}: {e}")
        return None


def _start_embedder_server(config: dict[str, Any], detached: bool = False) -> subprocess.Popen[Any] | None:
    embedder = config.get("embedder", {})
    api_base = embedder.get("api_base", "")
    if not api_base.startswith(("http://127.0.0.1", "http://localhost")):
        return None
    port = _get_port(api_base)
    model_name = embedder.get("model", "")
    ngl = embedder.get("n_gpu_layers", 0)
    model_path = _resolve_model_path(model_name)
    if model_path is None:
        print(f"[start] WARNING: Embedding model '{model_name}' not found")
        return None
    return _start_llama_server(model_path, port, ngl, 512, embeddings=True, pooling="mean", detached=detached)


def _start_llm_server(config: dict[str, Any], detached: bool = False) -> subprocess.Popen[Any] | None:
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
        print(f"[start] WARNING: LLM model '{model_name}' not found")
        return None
    return _start_llama_server(model_path, port, ngl, ctx_size, detached=detached)


def _check_llm_server(config: dict[str, Any]) -> bool:
    llm = config.get("llm", {})
    api_base = os.getenv("AI_LLM_API_BASE", llm.get("api_base", "http://127.0.0.1:8080/v1")).rstrip("/")
    if not is_port_in_use(_get_port(api_base)):
        return False
    try:
        resp = httpx.get(f"{api_base}/models", timeout=2.0)
        return resp.status_code < 500
    except Exception:
        return False


def _check_embedder_server(config: dict[str, Any]) -> bool:
    embedder = config.get("embedder", {})
    api_base = embedder.get("api_base", "http://127.0.0.1:8081/v1").rstrip("/")
    if not is_port_in_use(_get_port(api_base)):
        return False
    try:
        resp = httpx.get(f"{api_base}/models", timeout=2.0)
        return resp.status_code < 500
    except Exception:
        return False


def _start_uvicorn_background(host: str, port: int, project_root: Path, detached: bool = False) -> int:
    python = get_python_exe(project_root)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [python, "-m", "uvicorn", "ai_assistant.main:app", "--host", host, "--port", str(port)]
    kwargs = _prepare_subprocess_kwargs(port=port, detached=detached)
    kwargs["cwd"] = str(project_root)
    kwargs["env"] = env

    proc = subprocess.Popen(cmd, **kwargs)
    server_pid_file = project_root / "data" / "server.pid"
    server_pid_file.write_text(str(proc.pid), encoding="utf-8")
    return proc.pid


def main() -> int:
    parser = argparse.ArgumentParser(description="Start AI Assistant servers")
    parser.add_argument("--foreground", action="store_true", help="Keep in foreground, auto-cleanup on exit")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    print("[start] Starting...", flush=True)

    project_root = Path(__file__).parent.parent.resolve()
    (project_root / "data").mkdir(parents=True, exist_ok=True)

    # Очищаем старые PID-файлы перед стартом
    (project_root / "data" / "server.pid").unlink(missing_ok=True)
    (project_root / "data" / "llama-server.pid").unlink(missing_ok=True)

    config = get_config()
    port = args.port if args.port is not None else config.get("port", 8000)
    host = args.host if args.host is not None else config.get("host", "127.0.0.1")

    print(f"[start] host={host}, port={port}", flush=True)

    # Только в foreground режиме регистрируем cleanup при выходе
    if args.foreground:
        import atexit
        atexit.register(_cleanup_servers)

    import concurrent.futures
    def _ensure_llm() -> bool:
        if _check_llm_server(config):
            return True
        print("[start] LLM not detected — auto-starting...", flush=True)
        _start_llm_server(config, detached=not args.foreground)
        return _check_llm_server(config)

    def _ensure_emb() -> bool:
        if _check_embedder_server(config):
            return True
        print("[start] Embedder not detected — auto-starting...", flush=True)
        _start_embedder_server(config, detached=not args.foreground)
        return _check_embedder_server(config)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        llm_ok = pool.submit(_ensure_llm).result()
        emb_ok = pool.submit(_ensure_emb).result()

    if not llm_ok:
        print("[start] WARNING: LLM unavailable. Using mock/fallback.", flush=True)
    if not emb_ok:
        print("[start] WARNING: Embedder unavailable. RAG disabled.", flush=True)

    if is_port_in_use(port):
        print(f"[start] WARNING: Port {port} already in use!", flush=True)
        return 1

    print(f"[start] Starting uvicorn on {host}:{port}...", flush=True)
    pid = _start_uvicorn_background(host, port, project_root, detached=not args.foreground)

    time.sleep(1.0)
    if not is_port_in_use(port):
        print(f"[start] WARNING: Uvicorn did not bind quickly", flush=True)

    print(f"[start] Uvicorn PID: {pid}", flush=True)
    print(f"[start] Server ready at http://{host}:{port}", flush=True)

    if args.foreground:
        print("[start] Foreground mode — press Ctrl+C to stop", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("[start] Interrupted — cleaning up", flush=True)
            _cleanup_servers()
    else:
        print("[start] Background mode — servers detached from launcher", flush=True)
        print("[start] Run 'python scripts/stop.py' to stop", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
