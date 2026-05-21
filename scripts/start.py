#!/usr/bin/env python3
"""Start server — uvicorn + LLM API health check."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import yaml


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


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


def _check_llm_server(config: dict) -> None:
    """Check if LLM API is reachable — works with any OpenAI-compatible backend."""
    llm = config.get("llm", {})
    api_base = os.getenv(
        "AI_LLM_API_BASE",
        llm.get("api_base", "http://127.0.0.1:8080/v1")
    ).rstrip("/")

    print(f"[start] Checking LLM API at {api_base}...")
    try:
        resp = httpx.get(f"{api_base}/models", timeout=5.0)
        if resp.status_code < 500:
            print(f"[start] LLM API reachable")
            return
    except Exception as e:
        print(f"[start] LLM API not reachable: {e}")

    print(f"[start] WARNING: No LLM server detected at {api_base}")
    print("[start] Start your LLM server manually:")
    print("    llama-server:  llama-server.exe -m model.gguf --port 8080")
    print("    Ollama:        ollama serve")
    print("    vLLM:          python -m vllm.entrypoints.openai.api_server ...")
    print("[start] Or set AI_LLM_API_BASE env var to change the endpoint")


def main() -> int:
    project_root = Path(__file__).parent.parent.resolve()
    (project_root / "data").mkdir(parents=True, exist_ok=True)

    config = get_config()
    port = config.get("port", 8000)
    host = config.get("host", "127.0.0.1")

    _check_llm_server(config)

    if is_port_in_use(port):
        print(f"WARNING: Port {port} is already in use!")
        return 1

    pid_file = project_root / "data" / "server.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    python = get_python_exe(project_root)

    print(f"[start] Starting uvicorn on {host}:{port}")
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
