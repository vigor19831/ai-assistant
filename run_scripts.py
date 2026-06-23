#!/usr/bin/env python3
"""Run helper scripts from scripts/. Invoke from project root: python run_scripts.py"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"

# Auto-activate venv
_venv = Path(__file__).parent / ".venv"
_venv_py = _venv / PY
if _venv.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    if "--venv-relaunched" not in sys.argv:
        os.execl(str(_venv_py), str(_venv_py), *sys.argv, "--venv-relaunched")


def get_python(root: Path) -> str:
    return str(root / VENV / PY)


# Scripts excluded from the menu (setup, internal tools)
_EXCLUDED_SCRIPTS = frozenset({
    "setup.py",
    "__init__.py",
})

_DEV_SCRIPTS = frozenset({
    "check_all.py",
    "check_llm.py",
    "check_rag.py",
    "clean_cache.py",
    "context_build.py",
    "error_taxonomy_build.py",
    "open_shell.py",
    "structure.py",
})


def collect(root: Path, subdir: str) -> list[Path]:
    d = root / subdir
    return sorted(
        p for p in d.glob("*.py")
        if p.name not in _EXCLUDED_SCRIPTS
    )


def _sort(files: list[Path]) -> list[Path]:
    return sorted(files, key=lambda p: p.name)


def _fmt_duration(seconds: float) -> str:
    if seconds < 1.0:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60.0:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def _fmt_ago(timestamp: float) -> str:
    if timestamp == 0:
        return "never"
    delta = time.time() - timestamp
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def _get_docstring(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline()
            if first.startswith('"""'):
                line = f.readline().strip()
                return line.rstrip('"').strip()
    except Exception:
        pass
    return ""


def _load_history(root: Path) -> dict[str, dict[str, object]]:
    hist_file = root / "data" / ".run_history.json"
    try:
        with open(hist_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_history(root: Path, history: dict[str, dict[str, object]]) -> None:
    hist_file = root / "data" / ".run_history.json"
    try:
        hist_file.parent.mkdir(parents=True, exist_ok=True)
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass


def print_menu(scripts, history, last, last_time):
    NUM_W = 6
    NAME_W = 34
    COL_W = NUM_W + NAME_W + 4

    user = [s for s in scripts if s[0] not in _DEV_SCRIPTS]
    dev = [s for s in scripts if s[0] in _DEV_SCRIPTS]

    print()
    print(f"   SCRIPT RUNNER          {time.strftime('%H:%M:%S')}")
    print("  " + "-" * COL_W)

    idx = 1
    for name, path in user:
        is_last = (path == last)
        hist = history.get(path, {})
        status = hist.get("status", "")
        mark = "o" if status == "ok" else "x" if status == "fail" else "-"
        prefix = "* " if is_last else "  "
        server_mark = " [srv]" if name == "index_documents.py" else ""
        name_fmt = (name + server_mark)[:NAME_W]
        desc = _get_docstring(path)
        if desc:
            line = f"{name_fmt} - {desc[:22]}"
        else:
            line = name_fmt
        print(f"  {prefix}[{idx:2d}] {mark} {line}")
        idx += 1

    if dev:
        print("  " + "-" * COL_W)
        for name, path in dev:
            is_last = (path == last)
            hist = history.get(path, {})
            status = hist.get("status", "")
            mark = "o" if status == "ok" else "x" if status == "fail" else "-"
            prefix = "* " if is_last else "  "
            name_fmt = name[:NAME_W]
            desc = _get_docstring(path)
            if desc:
                line = f"[dev] {name_fmt} - {desc[:17]}"
            else:
                line = f"[dev] {name_fmt}"
            print(f"  {prefix}[{idx:2d}] {mark} {line}")
            idx += 1

    print("  " + "-" * COL_W)
    print("  [r] Rerun last" + " " * (COL_W - 16) + "[0] Exit")

    if last:
        last_name = Path(last).name
        if last_time is not None:
            print(f"\n  > Last: {last_name}  ({_fmt_duration(last_time)})")
        else:
            print(f"\n  > Last: {last_name}")
    else:
        print("\n  > No script run yet")
    print()


def run(py, target, root, extra, history):
    cmd = [py, target] + extra
    name = Path(target).name
    now = time.strftime("%H:%M:%S")

    print(f"\n  > Running: {name}  [{now}]")
    print(f"    {' '.join(cmd)}")

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

    print(f"\n  > {status}")
    input("\n  Press Enter... ")
    return res.returncode, elapsed


def main():
    root = Path(__file__).parent.resolve()
    py = get_python(root)

    raw = _sort(collect(root, "scripts"))
    user = [f for f in raw if f.name not in _DEV_SCRIPTS]
    dev = [f for f in raw if f.name in _DEV_SCRIPTS]
    ordered = user + dev
    scripts = [(f.name, str(f)) for f in ordered]

    history = _load_history(root)
    last = None
    last_time = None
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
                parts = choice.split()
                num = int(parts[0])
            except ValueError:
                print("  ? Invalid input")
                input("  Press Enter...")
                continue

            extra = parts[1:] if len(parts) > 1 else []

            found = False
            for i, (_, t) in enumerate(scripts, 1):
                if i == num:
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
