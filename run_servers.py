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
import types
from pathlib import Path
from typing import Any

VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"
_SEP = "─" * 50

# Fail-safe default when config.yaml omits `host`: loopback only —
# a missing key must not silently expose the API to the LAN.
HOST = "127.0.0.1"
API_PORT = 8000
LLM_PORT = 8080
EMBED_PORT = 8081
RERANK_PORT = 8082
PORTS = (LLM_PORT, EMBED_PORT, RERANK_PORT, API_PORT)

LLAMA_SERVER = "llama-server.exe" if os.name == "nt" else "llama-server"

TIMEOUT_START = 30.0
# SIGTERM/CTRL_BREAK -> force-kill ceiling. The lifespan shutdown
# persists indices first; a force-kill past this ceiling is safe —
# index writes are atomic (tmp + rename, core/io_utils).
STOP_GRACE_SECONDS = 10.0
LLAMA_LOG_MAX_BYTES = 10_485_760
# Fail-safe when config omits n_gpu_layers: CPU (0) — a missing
# field must not attempt full GPU offload (OOM on small-VRAM cards).
_NGL_DEFAULT = 0

# ── Auto-activate venv ───────────────────────────────────────────────────────
_venv = Path(__file__).parent / VENV
_venv_py = _venv / PY
if (
    _venv.exists()
    and _venv_py.exists()
    and Path(sys.executable).resolve() != _venv_py.resolve()
    and "--venv-relaunched" not in sys.argv
):
    _script = str(Path(__file__).resolve())
    if os.name == "nt":
        # subprocess.call keeps the console window on Windows double-click
        sys.exit(subprocess.call([str(_venv_py), _script, *sys.argv[1:]]))
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


def _run(
    cmd: list[str],
    log: Path | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.Popen[bytes]:
    """Start a detached child: stderr merged, log or /dev/null, own session."""
    # Heterogeneous kwargs bag by construction: no single value type
    # covers stdout/stdin/env/cwd/creationflags at once. Any is the
    # honest bag type; the return value stays strictly typed.
    kw: dict[str, Any] = {
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if log is not None:
        # SIM115: the handle is handed to the child process and
        # outlives this call by design (a server writes for hours).
        kw["stdout"] = open(log, "a", encoding="utf-8")  # noqa: SIM115
    else:
        kw["stdout"] = subprocess.DEVNULL
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP only: stop() addresses the child
        # alone via CTRL_BREAK_EVENT (graceful shutdown). CREATE_NO_WINDOW
        # was dropped: a hidden-console child cannot receive console
        # control events, silently degrading stop() to a hard kill. A
        # console child inherits ours — no new window, output is in logs.
        kw["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        )
    else:
        kw["start_new_session"] = True
    if env is not None:
        kw["env"] = env
    if cwd is not None:
        kw["cwd"] = cwd
    proc: subprocess.Popen[bytes] = subprocess.Popen(cmd, **kw)
    return proc


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


def _extra_args_safe(extra: list[Any] | None, server: str) -> bool:
    """drift #60: n_gpu_layers lives in config.yaml only; a duplicate
    -ngl in run_servers.yaml extra_args runs the server in an
    unpredictable mode. Refuse loudly instead of starting broken."""
    for arg in extra or []:
        s = str(arg)
        if s == "-ngl" or s.startswith("-ngl=") or s.startswith("--n-gpu-layers"):
            print(
                f"  ! {server}: extra_args carry '{s}' — remove it; "
                "n_gpu_layers belongs to config.yaml only (drift #60)"
            )
            return False
    return True


def _is_local_endpoint(component_cfg: dict[str, Any], port: int, name: str) -> bool:
    """True when the component points at OUR local server port.

    mock providers and cloud api_base endpoints need no local
    llama-server — the old 'model not found' warning was a false
    alarm for them."""
    if component_cfg.get("provider") == "mock":
        print(f"  > {name} provider is mock — no local server to start\n")
        return False
    api_base = str(component_cfg.get("api_base") or "")
    if f":{port}" not in api_base:
        print(
            f"  > {name} endpoint is {api_base or 'not set'} — "
            "no local server to start\n"
        )
        return False
    return True


def _report_ready(
    proc: subprocess.Popen[bytes], ready: bool, port: int, name: str, log: Path
) -> None:
    """Honest readiness: a port answer from a FOREIGN listener is not
    our server (our child died at startup); a timeout distinguishes a
    dead child from a slow one."""
    if ready:
        if proc.poll() is None:
            print(f"  + {name} ready  http://127.0.0.1:{port}\n")
        else:
            print(
                f"  ! Port {port} answered, but our {name} exited "
                f"(code {proc.returncode}) — another process holds "
                f"the port; see {log}\n"
            )
    elif proc.poll() is not None:
        print(
            f"  ! {name} exited at startup (code {proc.returncode}) "
            f"— see {log}\n"
        )
    else:
        print(f"  ! {name} did not respond in time — see {log}\n")


def _load_config(root: Path) -> dict[str, Any]:
    """Lazy import yaml — it lives inside the venv."""
    import yaml
    p = root / "config.yaml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _load_launch_config(root: Path) -> dict[str, Any]:
    """Load run_servers.yaml if present. Returns empty dict if missing."""
    launch_path = root / "run_servers.yaml"
    if not launch_path.exists():
        return {}
    import yaml
    with launch_path.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
        return data


def _wait_for_stop() -> None:
    print("\n  > Servers running. Press Enter or Ctrl+C to stop...")
    input()
    print()


def _pid_alive(pid: int) -> bool:
    """True if *pid* exists. os.kill(pid, 0) kills the process on Windows."""
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, check=False
        ).stdout
        return str(pid) in out.decode(errors="replace")
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


# ── Server lifecycle ─────────────────────────────────────────────────────────
def _start_llm_server(
    cfg: dict[str, Any], launch: dict[str, Any], root: Path, llama_log: Path
) -> None:
    llm_cfg: dict[str, Any] = cfg.get("llm", {})
    if not _is_local_endpoint(llm_cfg, LLM_PORT, "LLM"):
        return
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
        "-ngl", str(llm_cfg.get("n_gpu_layers", _NGL_DEFAULT)),
        "-c", str(llm_cfg.get("server_context_size", 4096)),
    ]
    # Low-level arguments now come exclusively from run_servers.yaml
    extra = launch.get("llm", {}).get("extra_args", [])
    if not _extra_args_safe(extra, "llm"):
        return
    if extra:
        cmd.extend(extra)
    proc = _run(cmd, llama_log)
    _report_ready(proc, wait_port(LLM_PORT), LLM_PORT, "LLM", llama_log)


def _start_embedder(
    cfg: dict[str, Any], launch: dict[str, Any], root: Path, llama_log: Path
) -> None:
    emb_cfg: dict[str, Any] = cfg.get("embedder", {})
    if not _is_local_endpoint(emb_cfg, EMBED_PORT, "Embedder"):
        return
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
        "-ngl", str(emb_cfg.get("n_gpu_layers", _NGL_DEFAULT)),
        "-c", "512", "--embedding", "--pooling", "mean",
    ]
    extra = launch.get("embedder", {}).get("extra_args", [])
    if not _extra_args_safe(extra, "embedder"):
        return
    if extra:
        cmd.extend(extra)
    proc = _run(cmd, llama_log)
    _report_ready(proc, wait_port(EMBED_PORT), EMBED_PORT, "Embedder", llama_log)


def _start_reranker(
    cfg: dict[str, Any], launch: dict[str, Any], root: Path, llama_log: Path
) -> None:
    rerank_cfg: dict[str, Any] = cfg.get("reranker", {})
    if not _is_local_endpoint(rerank_cfg, RERANK_PORT, "Reranker"):
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
        "-ngl", str(rerank_cfg.get("n_gpu_layers", _NGL_DEFAULT)),
        "-c", "2048", "--rerank",
    ]
    extra = launch.get("reranker", {}).get("extra_args", [])
    if not _extra_args_safe(extra, "reranker"):
        return
    if extra:
        cmd.extend(extra)
    proc = _run(cmd, llama_log)
    _report_ready(proc, wait_port(RERANK_PORT), RERANK_PORT, "Reranker", llama_log)


def _start_api(cfg: dict[str, Any], root: Path, py: str) -> None:
    host = cfg.get("host", HOST)
    port = cfg.get("port", API_PORT)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")

    print(f"  > API server  uvicorn {host}:{port}")
    cmd = [
        py, "-m", "uvicorn", "ai_assistant.main:app",
        "--host", host, "--port", str(port),
    ]
    proc = _run(
        cmd, root / "data" / f"server_{port}.log", env=env, cwd=str(root)
    )
    (root / "data" / "uvicorn.pid").write_text(str(proc.pid), encoding="utf-8")

    if wait_port(port):
        print(f"  + API ready  http://{host}:{port}")
        print(f"    PID {proc.pid} — born now; fresh code guaranteed\n")
    else:
        print(f"  ! API did not respond on port {port}\n")


def start(root: Path) -> int:
    print("\n  Starting servers")
    print(f"  {_SEP}")

    pid_file = root / "data" / "uvicorn.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            if not _pid_alive(pid):
                raise ProcessLookupError(f"PID {pid} is not running")
            print(f"\n  ! Server already running (PID {pid})")
            print("    Nothing was started or restarted.")
            print("    To apply code changes: stop, then start.")
            # When the live server was born — compare with your last
            # code edit in one glance (the day's trap: a stale process
            # mistaken for "code not applied").
            try:
                out = subprocess.run(
                    ["ps", "-o", "lstart=", "-p", str(pid)],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
                if out:
                    print(f"    Live server started: {out}")
            except OSError:
                pass
            print("    Use: python run_servers.py stop\n")
            return 1
        except (ProcessLookupError, ValueError, OSError):
            print("  > Removed stale PID file")
            pid_file.unlink(missing_ok=True)

    # Venv FIRST: config loading needs yaml (venv-only), and no
    # server may start without a venv.
    venv_py = _ensure_venv(root)
    if venv_py is None:
        return 1

    cfg = _load_config(root)
    launch = _load_launch_config(root)

    # Default-key guard: the example key 'local' on a non-loopback
    # interface would silently expose the API to the network.
    sec = cfg.get("security") or {}
    host = cfg.get("host", HOST)
    if (
        isinstance(sec, dict)
        and sec.get("api_key") == "local"
        and host not in ("127.0.0.1", "localhost", "::1")
    ):
        print(
            f"  ! Refusing to start: default security.api_key 'local' "
            f"with host {host}"
        )
        print(
            "    Set a real key in config.yaml or bind to 127.0.0.1 "
            "(local-first profile)."
        )
        return 1

    (root / "data").mkdir(exist_ok=True)

    llama_log = root / "data" / "llama.log"
    if llama_log.exists() and llama_log.stat().st_size > LLAMA_LOG_MAX_BYTES:
        # Never rotate while a server may still hold the file open:
        # on Linux the unlink is silent and the process keeps writing
        # into a deleted inode (drift #74). Ports are the behavioral
        # guard, not the OS.
        if any(not port_free(p) for p in (LLM_PORT, EMBED_PORT, RERANK_PORT)):
            print("  ! llama.log over size — a server still runs; stop first")
        else:
            llama_log.unlink()

    try:
        _start_llm_server(cfg, launch, root, llama_log)
        _start_embedder(cfg, launch, root, llama_log)
        _start_reranker(cfg, launch, root, llama_log)

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
        except ValueError:
            pid = 0
        if pid > 0 and _pid_alive(pid):
            try:
                if os.name == "nt":
                    # CTRL_BREAK_EVENT reaches a child started with
                    # CREATE_NEW_PROCESS_GROUP in our console; uvicorn
                    # runs its graceful lifespan shutdown (index save).
                    os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    os.kill(pid, signal.SIGTERM)
            except OSError:
                pass  # gone or undeliverable — the force path below
            # Ctrl+C during the grace window means "force now", not
            # "abort stop halfway" (llama servers would stay up).
            try:
                deadline = time.time() + STOP_GRACE_SECONDS
                while _pid_alive(pid) and time.time() < deadline:
                    time.sleep(0.2)
            except KeyboardInterrupt:
                pass
            if _pid_alive(pid):
                print("  ! Graceful shutdown did not finish — forcing")
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                    )
                else:
                    with contextlib.suppress(OSError):
                        os.kill(pid, signal.SIGKILL)
        else:
            print("  > Process already stopped (stale PID file)")
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
            if os.name == "nt":
                cmd = ["taskkill", "/F", "/IM", name]
            else:
                cmd = ["pkill", "-f", name]
            subprocess.run(cmd, capture_output=True)

    for port in PORTS:
        if os.name == "nt":
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                # Aligned with kill.py: match the LOCAL address only
                # (endswith) and LISTENING sockets — the old substring
                # match also killed clients of the port.
                if "LISTENING" not in line:
                    continue
                if f":{port}" not in line:
                    continue
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                if not parts[1].endswith(f":{port}"):
                    continue
                try:
                    pid = int(parts[-1])
                except ValueError:
                    continue
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                )
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
    still_held = [p for p in PORTS if not port_free(p)]
    if still_held:
        print(f"  ! Ports still held: {still_held}")
        return 1
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    root = Path(__file__).parent.resolve()

    # Graceful Ctrl+C — raise KeyboardInterrupt instead of default traceback
    def _on_sigint(
        _signum: int, _frame: types.FrameType | None
    ) -> None:
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
