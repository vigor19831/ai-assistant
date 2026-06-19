#!/usr/bin/env python3
"""AI Assistant — запуск и остановка серверов.

Usage:
    python run_servers.py start   # запуск всех серверов (по умолчанию)
    python run_servers.py stop    # остановка
    python run_servers.py kill    # аварийное завершение всех процессов
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# 0. SELF-REEXEC — must be FIRST, before any imports that need venv packages
# ═══════════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).parent.resolve()
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _ensure_venv() -> Path:
    """Return path to venv python. If venv missing — print instructions and exit."""
    if VENV_PY.exists():
        return VENV_PY

    pip = VENV / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")
    print("=" * 60)
    print("  Virtual environment not found!")
    print()
    print("  Install it with:")
    print()
    print(f"    cd {ROOT}")
    print(f"    {sys.executable} -m venv .venv")
    print(f"    {pip} install -e .")
    print()
    print("  Then run this script again.")
    print("=" * 60)

    if os.name == "nt" and sys.stdout.isatty():
        input("\nPress Enter to exit...")
    sys.exit(1)


def _reexec_if_needed() -> None:
    """If running from system python, restart self via venv python."""
    venv_py = _ensure_venv()
    current = Path(sys.executable).resolve()
    target = venv_py.resolve()

    if current == target:
        return

    cmd = [str(target), str(__file__)] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))


# Execute immediately — before any third-party imports
_reexec_if_needed()

# ═══════════════════════════════════════════════════════════════════════════════
# Now we are GUARANTEED to run inside .venv — safe to import anything
# ═══════════════════════════════════════════════════════════════════════════════

import yaml  # noqa: E402


def _run(cmd: list[str], log: Path | None = None, **kwargs) -> subprocess.Popen:
    kw = {
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if log:
        kw["stdout"] = open(log, "a", encoding="utf-8")  # noqa: SIM115
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


def wait_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_free(port):
            return True
        time.sleep(0.3)
    return False


def _find_exe(name: str) -> Path | None:
    for p in [
        ROOT / "vendor" / "llama" / name,
        ROOT / "vendor" / "llama.cpp" / "build" / "bin" / name,
    ]:
        if p.exists():
            return p
    found = shutil.which(name)
    return Path(found) if found else None


def _find_model(name: str) -> Path | None:
    d = ROOT / "vendor" / "models"
    if not d.exists():
        return None
    for ext in (".gguf", ".GGUF"):
        if (d / f"{name}{ext}").exists():
            return d / f"{name}{ext}"
    for f in d.iterdir():
        if f.suffix.lower() == ".gguf" and name.lower() in f.name.lower():
            return f
    return None


def _load_config() -> dict:
    p = ROOT / "config.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _wait_for_stop() -> None:
    """Block until user presses Enter or Ctrl+C."""
    print("\nServers running. Press Enter or Ctrl+C to stop...")
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        input()
    print()


def start() -> int:
    # Clean stale PID file before starting
    pid_file = ROOT / "data" / "uvicorn.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)  # Check if process is alive
            print(f"[!] Server already running (PID {pid})")
            print("    Use: python run_servers.py stop")
            return 1
        except (ProcessLookupError, ValueError, OSError):
            print("[*] Removed stale PID file")
            pid_file.unlink(missing_ok=True)

    cfg = _load_config()
    (ROOT / "data").mkdir(exist_ok=True)

    py = str(VENV_PY)

    # ── LLM server ──
    llm_cfg = cfg.get("llm", {})
    model = _find_model(llm_cfg.get("model", ""))
    if model:
        exe = _find_exe("llama-server.exe" if os.name == "nt" else "llama-server")
        if exe:
            cmd = [
                str(exe), "-m", str(model),
                "--host", "127.0.0.1", "--port", "8080",
                "-ngl", str(llm_cfg.get("n_gpu_layers", 99)),
                "-c", str(llm_cfg.get("server_context_size", 4096)),
            ]
            _run(cmd, ROOT / "data" / "server_8080.log")
            if wait_port(8080):
                print("[+] LLM server: http://127.0.0.1:8080")
            else:
                print("[!] LLM server did not respond")

    # ── Embedder server ──
    emb_cfg = cfg.get("embedder", {})
    model = _find_model(emb_cfg.get("model", ""))
    if model:
        exe = _find_exe("llama-server.exe" if os.name == "nt" else "llama-server")
        if exe:
            cmd = [
                str(exe), "-m", str(model),
                "--host", "127.0.0.1", "--port", "8081",
                "-ngl", str(emb_cfg.get("n_gpu_layers", 99)),
                "-c", "512", "--embedding", "--pooling", "mean",
            ]
            _run(cmd, ROOT / "data" / "server_8081.log")
            if wait_port(8081):
                print("[+] Embedder server: http://127.0.0.1:8081")
            else:
                print("[!] Embedder server did not respond")

    # ── Uvicorn API ──
    host = cfg.get("host", "0.0.0.0")
    port = cfg.get("port", 8000)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [py, "-m", "uvicorn", "ai_assistant.main:app", "--host", host, "--port", str(port)]
    proc = _run(cmd, ROOT / "data" / "server_8000.log", env=env, cwd=str(ROOT))
    (ROOT / "data" / "uvicorn.pid").write_text(str(proc.pid), encoding="utf-8")

    if wait_port(port):
        print(f"[+] API server: http://{host}:{port}")
    else:
        print(f"[!] API server did not respond on port {port}")

    _wait_for_stop()
    return stop()


def stop() -> int:
    print("\n[+] Stopping...")

    pid_file = ROOT / "data" / "uvicorn.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            try:
                os.kill(pid, 0)  # Check if process exists
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                    # Still alive — force kill
                    if hasattr(signal, "SIGKILL"):
                        os.kill(pid, signal.SIGKILL)
                    elif os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True,
                        )
                except ProcessLookupError:
                    pass  # Died gracefully
            except ProcessLookupError:
                pass  # Already dead — just remove file
        except (ValueError, OSError):
            pass  # Bad PID file — remove it
        finally:
            pid_file.unlink(missing_ok=True)
            print("  ✓ PID file removed")

    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
        time.sleep(0.3)
        subprocess.run(["pkill", "-9", "-f", "llama-server"], capture_output=True)

    print("[+] Done.")
    return 0


def kill_main() -> int:
    """Emergency kill switch — kills all project processes and frees ports."""
    print("=" * 50)
    print("  Emergency Kill Switch")
    print("=" * 50)

    # Kill by name
    names = ("llama-server.exe", "llama-server", "uvicorn")
    for name in names:
        if shutil.which("taskkill" if os.name == "nt" else "pkill"):
            cmd = (["taskkill", "/F", "/IM", name] if os.name == "nt"
                   else ["pkill", "-f", name])
            subprocess.run(cmd, capture_output=True)

    # Kill by port
    for port in (8080, 8081, 8000):
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
            for cmd in (["lsof", "-ti", f":{port}"], ["fuser", f"{port}/tcp"]):
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        pid = int(result.stdout.strip().split()[0])
                        os.kill(pid, signal.SIGKILL)
                    except (ValueError, OSError):
                        continue

    # Clean PID file
    pid_file = ROOT / "data" / "uvicorn.pid"
    pid_file.unlink(missing_ok=True)

    print("\n[+] Done.")
    return 0


def _pause_on_error() -> None:
    """Pause before exit on Windows when launched by double-click."""
    if os.name == "nt" and sys.stdout.isatty():
        input("\nPress Enter to exit...")


def main() -> int:
    try:
        cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
        if cmd == "kill":
            return kill_main()
        if cmd == "start":
            return start()
        if cmd == "stop":
            return stop()
        print(f"Unknown command: {cmd}")
        print("Usage: python run_servers.py [start|stop|kill]")
        return 1
    except Exception as exc:
        log_path = ROOT / "data" / "run_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        import traceback
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Error: {exc}\n")
            f.write(traceback.format_exc())
        print(f"\n[!] Error: {exc}")
        print(f"    Details: {log_path}")
        _pause_on_error()
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log_path = ROOT / "data" / "run_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        _pause_on_error()
        sys.exit(1)
