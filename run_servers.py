#!/usr/bin/env python3
"""AI Assistant — start and stop servers.

Usage:
    python run_servers.py start   # start all servers (default)
    python run_servers.py stop    # stop
    python run_servers.py kill    # emergency kill all processes
"""

import contextlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"
_SEP = "─" * 50

HOST = "0.0.0.0"
API_PORT = 8000
LLM_PORT = 8080
EMBED_PORT = 8081
RERANK_PORT = 8082
PORTS = (LLM_PORT, EMBED_PORT, RERANK_PORT, API_PORT)

LLAMA_SERVER = "llama-server.exe" if os.name == "nt" else "llama-server"

TIMEOUT_START = 30.0
LLAMA_LOG_MAX_BYTES = 10_485_760

# ── Auto-activate venv ───────────────────────────────────────────────────────
_venv = Path(__file__).parent / VENV
_venv_py = _venv / PY
if _venv.exists() and _venv_py.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    if "--venv-relaunched" not in sys.argv:
        _script = str(Path(__file__).resolve())
        if os.name == "nt":
            # subprocess.call keeps the console window on Windows double-click
            sys.exit(subprocess.call([str(_venv_py), _script] + sys.argv[1:]))
        else:
            os.execl(
                str(_venv_py), str(_venv_py),
                _script, *sys.argv[1:], "--venv-relaunched",
            )


# ── Helpers ──────────────────────────────────────────────────────────────────
def _ensure_venv(root: Path) -> Path | None:
    """Return venv python path, or None if missing."""
    venv_py = root / VENV / PY
    if venv_py.exists():
        return venv_py
    pip = root / VENV / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")
    print("Virtual environment not found!")
    print(f"  cd {root}")
    print(f"  {sys.executable} -m venv .venv")
    print(f"  {pip} install -e .")
    return None


def _run(cmd: list[str], log: Path | None = None, **kwargs) -> subprocess.Popen:
    kw: dict[str, object] = {
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if log is not None:
        kw["stdout"] = open(log, "a", encoding="utf-8")
    else:
        kw["stdout"] = subprocess.DEVNULL
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    kw.update(kwargs)
    return subprocess.Popen(cmd, **kw)


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_port(port: int, timeout: float = TIMEOUT_START) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_free(port):
            return True
        time.sleep(0.3)
    return False


def _find_exe(name: str, root: Path) -> Path | None:
    for p in [
        root / "vendor" / "llama" / name,
        root / "vendor" / "llama.cpp" / "build" / "bin" / name,
    ]:
        if p.exists():
            return p
    found = shutil.which(name)
    return Path(found) if found else None


def _find_model(name: str, root: Path) -> Path | None:
    d = root / "vendor" / "models"
    if not d.exists():
        return None
    for ext in (".gguf", ".GGUF"):
        if (d / f"{name}{ext}").exists():
            return d / f"{name}{ext}"
    for f in d.iterdir():
        if f.suffix.lower() == ".gguf" and name.lower() in f.name.lower():
            return f
    return None


def _load_config(root: Path) -> dict:
    """Lazy import yaml — it lives inside the venv."""
    import yaml
    p = root / "config.yaml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _wait_for_stop() -> None:
    print("\n  > Servers running. Press Enter or Ctrl+C to stop...")
    input()
    print()


# ── Server lifecycle ─────────────────────────────────────────────────────────
def _start_llm_server(cfg: dict, root: Path, llama_log: Path) -> None:
    llm_cfg: dict = cfg.get("llm", {})
    model = _find_model(llm_cfg.get("model", ""), root)
    if not model:
        print("  ! LLM model not found\n")
        return
    exe = _find_exe(LLAMA_SERVER, root)
    if not exe:
        print("  ! llama-server not found\n")
        return
    print(f"\n  > LLM server  model={model.name}")
    cmd = [
        str(exe), "-m", str(model),
        "--host", "127.0.0.1", "--port", str(LLM_PORT),
        "-ngl", str(llm_cfg.get("n_gpu_layers", 99)),
        "-c", str(llm_cfg.get("server_context_size", 4096)),
        "-lv", "1",
    ]
    _run(cmd, llama_log)
    if wait_port(LLM_PORT):
        print(f"  + LLM ready  http://127.0.0.1:{LLM_PORT}\n")
    else:
        print("  ! LLM did not respond\n")


def _start_embedder(cfg: dict, root: Path, llama_log: Path) -> None:
    emb_cfg: dict = cfg.get("embedder", {})
    model = _find_model(emb_cfg.get("model", ""), root)
    if not model:
        print("  ! Embedder model not found\n")
        return
    exe = _find_exe(LLAMA_SERVER, root)
    if not exe:
        print("  ! llama-server not found\n")
        return
    print(f"  > Embedder server  model={model.name}")
    cmd = [
        str(exe), "-m", str(model),
        "--host", "127.0.0.1", "--port", str(EMBED_PORT),
        "-ngl", str(emb_cfg.get("n_gpu_layers", 99)),
        "-c", "512", "--embedding", "--pooling", "mean",
        "-lv", "1",
    ]
    _run(cmd, llama_log)
    if wait_port(EMBED_PORT):
        print(f"  + Embedder ready  http://127.0.0.1:{EMBED_PORT}\n")
    else:
        print("  ! Embedder did not respond\n")


def _start_reranker(cfg: dict, root: Path, llama_log: Path) -> None:
    rerank_cfg: dict = cfg.get("reranker", {})
    if rerank_cfg.get("provider") != "local":
        return
    model = _find_model(rerank_cfg.get("model", ""), root)
    if not model:
        print("  ! Reranker model not found\n")
        return
    exe = _find_exe(LLAMA_SERVER, root)
    if not exe:
        print("  ! llama-server not found\n")
        return
    print(f"  > Reranker server  model={model.name}")
    cmd = [
        str(exe), "-m", str(model),
        "--host", "127.0.0.1", "--port", str(RERANK_PORT),
        "-ngl", str(rerank_cfg.get("n_gpu_layers", 99)),
        "-c", "2048", "--rerank",
        "-lv", "1",
    ]
    _run(cmd, llama_log)
    if wait_port(RERANK_PORT):
        print(f"  + Reranker ready  http://127.0.0.1:{RERANK_PORT}\n")
    else:
        print("  ! Reranker did not respond\n")


def _start_api(cfg: dict, root: Path, py: str) -> None:
    host = cfg.get("host", HOST)
    port = cfg.get("port", API_PORT)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    print(f"  > API server  uvicorn {host}:{port}")
    cmd = [py, "-m", "uvicorn", "ai_assistant.main:app", "--host", host, "--port", str(port)]
    proc = _run(cmd, root / "data" / "server_8000.log", env=env, cwd=str(root))
    (root / "data" / "uvicorn.pid").write_text(str(proc.pid), encoding="utf-8")

    if wait_port(port):
        print(f"  + API ready  http://{host}:{port}\n")
    else:
        print(f"  ! API did not respond on port {port}\n")


def start(root: Path) -> int:
    print("\n  Starting servers")
    print(f"  {_SEP}")

    pid_file = root / "data" / "uvicorn.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            print(f"  ! Server already running (PID {pid})")
            print("    Use: python run_servers.py stop")
            return 1
        except (ProcessLookupError, ValueError, OSError):
            print("  > Removed stale PID file")
            pid_file.unlink(missing_ok=True)

    cfg = _load_config(root)
    (root / "data").mkdir(exist_ok=True)

    llama_log = root / "data" / "llama.log"
    if llama_log.exists() and llama_log.stat().st_size > LLAMA_LOG_MAX_BYTES:
        llama_log.unlink()

    try:
        _start_llm_server(cfg, root, llama_log)
        _start_embedder(cfg, root, llama_log)
        _start_reranker(cfg, root, llama_log)

        venv_py = _ensure_venv(root)
        if venv_py is None:
            return 1
        _start_api(cfg, root, str(venv_py))

        _wait_for_stop()
    except (KeyboardInterrupt, EOFError):
        print("\n  ! Interrupted.")
    return stop(root)


def stop(root: Path) -> int:
    print("\n  Stopping servers")
    print(f"  {_SEP}")

    pid_file = root / "data" / "uvicorn.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, 0)
                if hasattr(signal, "SIGKILL"):
                    os.kill(pid, signal.SIGKILL)
                elif os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        except (ValueError, OSError, ProcessLookupError):
            pass
        finally:
            pid_file.unlink(missing_ok=True)
            print("  + PID file removed")

    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/IM", LLAMA_SERVER], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
        time.sleep(0.3)
        subprocess.run(["pkill", "-9", "-f", "llama-server"], capture_output=True)

    print("  + Done.")
    return 0


def kill_main(root: Path) -> int:
    print("\n  Emergency Kill Switch")
    print(f"  {_SEP}")

    names = (LLAMA_SERVER, "uvicorn")
    for name in names:
        if shutil.which("taskkill" if os.name == "nt" else "pkill"):
            cmd = (["taskkill", "/F", "/IM", name] if os.name == "nt" else ["pkill", "-f", name])
            subprocess.run(cmd, capture_output=True)

    for port in PORTS:
        if os.name == "nt":
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if f":{port}" in line and ("LISTENING" in line or "ESTABLISHED" in line):
                    parts = line.strip().split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                        except ValueError:
                            continue
        else:
            for probe in (["lsof", "-ti", f":{port}"], ["fuser", f"{port}/tcp"]):
                result = subprocess.run(probe, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        pid = int(result.stdout.strip().split()[0])
                        os.kill(pid, signal.SIGKILL)
                    except (ValueError, OSError):
                        continue

    (root / "data" / "uvicorn.pid").unlink(missing_ok=True)
    print("  + Done.")
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    root = Path(__file__).parent.resolve()

    def _on_sigint(_signum: int, _frame) -> None:
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, _on_sigint)

    # Strip internal --venv-relaunched flag
    args = [a for a in sys.argv[1:] if a != "--venv-relaunched"]
    # On Unix os.execl injects the script path as sys.argv[1]; skip it.
    if args and Path(args[0]).name == Path(__file__).name:
        args = args[1:]

    try:
        cmd = args[0] if args else "start"
        if cmd == "kill":
            return kill_main(root)
        if cmd == "start":
            return start(root)
        if cmd == "stop":
            return stop(root)
        print(f"Unknown command: {cmd}")
        print("Usage: python run_servers.py [start|stop|kill]")
        return 1
    except EOFError:
        print("\n  ! Input stream closed. Exiting.")
        return 1
    except KeyboardInterrupt:
        print("\n  ! Interrupted by user. Exiting.")
        return 0
    except Exception as exc:
        log_path = root / "data" / "run_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Error: {exc}\n")
            f.write(traceback.format_exc())
        print(f"\n  ! Error: {exc}")
        print(f"    Details: {log_path}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
