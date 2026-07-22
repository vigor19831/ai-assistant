#!/usr/bin/env python3
"""Run helper scripts from scripts/. Invoke from project root: python run_scripts.py"""

import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"
_SEP = "─" * 50

# ── Auto-activate venv ───────────────────────────────────────────────────────
_venv = Path(__file__).parent / VENV
_venv_py = _venv / PY
if _venv.exists() and _venv_py.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    if "--venv-relaunched" not in sys.argv:
        os.execl(str(_venv_py), str(_venv_py), *sys.argv, "--venv-relaunched")


# ── Helpers ──────────────────────────────────────────────────────────────────
def get_python(root: Path) -> str:
    """Return venv python if available, otherwise system python."""
    venv_py = root / VENV / PY
    return str(venv_py) if venv_py.exists() else sys.executable


_EXCLUDED_SCRIPTS = frozenset({"setup.py", "__init__.py"})


def collect_scripts(root: Path, subdir: str = "scripts") -> list[Path]:
    """Return sorted list of runnable scripts, excluding internal files."""
    d = root / subdir
    if not d.exists():
        return []
    return sorted(
        p for p in d.glob("*.py")
        if p.name not in _EXCLUDED_SCRIPTS
    )


def _fmt_duration(seconds: float) -> str:
    if seconds < 1.0:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60.0:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def _history_path(root: Path) -> Path:
    return root / "data" / ".run_history.json"


def _load_history(root: Path) -> dict[str, dict]:
    hist_file = _history_path(root)
    if not hist_file.exists():
        return {}
    try:
        with open(hist_file, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(root: Path, history: dict) -> None:
    """Atomic write: temp file + rename to avoid corruption on crash."""
    hist_file = _history_path(root)
    tmp_path: Path | None = None
    try:
        hist_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=hist_file.parent,
            prefix=".run_history_tmp_", suffix=".json", delete=False,
        ) as tmp:
            json.dump(history, tmp, indent=2)
            tmp_path = Path(tmp.name)
        tmp_path.replace(hist_file)
        tmp_path = None  # Successfully moved, no cleanup needed
    except Exception:
        pass
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


# ── UI ───────────────────────────────────────────────────────────────────────
def print_menu(
    scripts: list[tuple[str, str]],
    history: dict,
    last: str | None,
    last_time: float | None,
) -> None:
    print()
    print(_SEP)
    print(f"   SCRIPT RUNNER          {time.strftime('%H:%M:%S')}")
    print(_SEP)

    if not scripts:
        print("  (no scripts found in scripts/)")
    else:
        for idx, (name, path) in enumerate(scripts, 1):
            is_last = (path == last)
            hist = history.get(path, {})
            status = hist.get("status", "")
            mark = "o" if status == "ok" else "x" if status == "fail" else "-"
            prefix = "* " if is_last else "  "
            print(f"  {prefix}[{idx:2d}] {mark} {name[:34]}")

    print(_SEP)
    print("  [r] Rerun last  [0] Exit")

    if last:
        last_name = Path(last).name
        if last_time is not None:
            print(f"\n  > Last: {last_name}  ({_fmt_duration(last_time)})")
        else:
            print(f"\n  > Last: {last_name}")
    else:
        print("\n  > No script run yet")
    print(_SEP)
    print()


def run(
    py: str,
    target: str,
    root: Path,
    extra: list[str],
    history: dict,
) -> tuple[int, float]:
    cmd = [py, target] + extra
    name = Path(target).name
    now = time.strftime("%H:%M:%S")

    print()
    print(_SEP)
    print(f"  RUN: {name}")
    print(f"  TIME: {now}")
    print(f"  {' '.join(cmd)}")
    print(_SEP)
    print()

    start = time.perf_counter()
    res = subprocess.run(cmd, cwd=root)
    elapsed = time.perf_counter() - start

    if res.returncode == 0:
        status = f"OK  ({_fmt_duration(elapsed)})"
        history[target] = {"status": "ok", "time": time.time()}
    else:
        status = f"FAIL (exit {res.returncode})  ({_fmt_duration(elapsed)})"
        history[target] = {"status": "fail", "time": time.time()}

    _save_history(root, history)

    print()
    print(_SEP)
    print(f"  RESULT: {status}")
    print(_SEP)
    print()
    input("  Press Enter... ")
    return res.returncode, elapsed


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    root = Path(__file__).parent.resolve()
    py = get_python(root)

    scripts = [(f.name, str(f)) for f in collect_scripts(root)]
    history = _load_history(root)
    last: str | None = None
    last_time: float | None = None

    # Graceful Ctrl+C — raise KeyboardInterrupt instead of default traceback
    def _on_sigint(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, _on_sigint)

    while True:
        try:
            print_menu(scripts, history, last, last_time)
            choice = input("  Enter: ").strip()

            if choice in ("0", "exit", "q", "quit"):
                print("\n  Bye.\n")
                return 0

            if choice == "r" and last:
                _, last_time = run(py, last, root, [], history)
                continue

            try:
                parts = shlex.split(choice)
                num = int(parts[0])
            except ValueError:
                print("  ? Invalid input")
                input("  Press Enter...")
                continue

            extra = parts[1:] if len(parts) > 1 else []

            found = False
            for idx_script, (_, t) in enumerate(scripts, 1):
                if idx_script == num:
                    last = t
                    _, last_time = run(py, t, root, extra, history)
                    found = True
                    break

            if not found:
                print(f"  ? No script #{num}")
                input("  Press Enter...")

        except EOFError:
            print("\n  ! Input stream closed. Exiting.")
            return 1
        except KeyboardInterrupt:
            print("\n  ! Interrupted by user. Exiting.")
            return 0
        except Exception as e:
            print(f"\n  ! Unexpected error: {e}")
            try:
                input("  Press Enter to continue...")
            except EOFError:
                return 1


if __name__ == "__main__":
    sys.exit(main())
