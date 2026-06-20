#!/usr/bin/env python3
"""Run helper scripts from scripts/ and tests/. Invoke from project root: python run_scripts.py"""

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
    # Защита от бесконечной рекурсии, если пути ведут себя странно
    if "--venv-relaunched" not in sys.argv:
        os.execl(str(_venv_py), str(_venv_py), *sys.argv, "--venv-relaunched")


def get_python(root: Path) -> str:
    return str(root / VENV / PY)


def collect(root: Path, subdir: str) -> list[Path]:
    d = root / subdir
    return sorted(p for p in d.glob("*.py") if p.name != "__init__.py")


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


def print_menu(scripts, tests, last, last_time):
    NUM_W = 6
    NAME_W = 26
    COL_W = NUM_W + NAME_W
    GAP = 4
    TOTAL_W = COL_W + GAP + COL_W

    max_rows = max(len(scripts), len(tests))
    rows = [(scripts[i] if i < len(scripts) else None,
             tests[i] if i < len(tests) else None) for i in range(max_rows)]

    print()
    print("   SCRIPT RUNNER")
    print()
    print("  scripts/" + " " * (TOTAL_W - 10) + "tests/")
    print("  " + "-" * COL_W + " " * GAP + "-" * COL_W)

    for left, right in rows:
        line = "  "

        if left:
            n, name, path = left
            is_last = (path == last)
            num = f"[{n:2d}]"
            name = name[:NAME_W - 1] + "…" if len(name) > NAME_W else name
            if is_last:
                cell = f"* {num} {name}"
            else:
                cell = f"  {num} {name}"
            line += cell.ljust(COL_W)
        else:
            line += " " * COL_W

        line += " " * GAP

        if right:
            n, name, path = right
            is_last = (path == last)
            num = f"[{n:2d}]"
            name = name[:NAME_W - 1] + "…" if len(name) > NAME_W else name
            if is_last:
                cell = f"* {num} {name}"
            else:
                cell = f"  {num} {name}"
            line += cell.ljust(COL_W)
        else:
            line += " " * COL_W

        print(line)

    print("  " + "-" * TOTAL_W)
    print("  [r] Rerun last" + " " * (TOTAL_W // 2 - 14) + "[0] Exit")

    if last:
        last_name = Path(last).name
        if last_time is not None:
            print(f"  > Last: {last_name}  ({_fmt_duration(last_time)})")
        else:
            print(f"  > Last: {last_name}")
    else:
        print("  > No script run yet")
    print()


def run(py, target, root, extra):
    cmd = [py, target] + extra
    name = Path(target).name

    print(f"\n  > Running: {name}")
    print(f"    {' '.join(cmd)}")

    start = time.perf_counter()
    res = subprocess.run(cmd, cwd=root)
    elapsed = time.perf_counter() - start

    if res.returncode == 0:
        status = f"OK  ({_fmt_duration(elapsed)})"
    else:
        status = f"FAIL (exit {res.returncode})  ({_fmt_duration(elapsed)})"

    print(f"\n  > {status}")
    input("\n  Press Enter... ")
    return res.returncode, elapsed


def main():
    root = Path(__file__).parent.resolve()
    py = get_python(root)

    scripts = [(i + 1, f.name, str(f)) for i, f in enumerate(_sort(collect(root, "scripts")))]
    tests = [(i + len(scripts) + 1, f.name, str(f)) for i, f in enumerate(_sort(collect(root, "tests")))]

    last = None
    last_time = None
    while True:
        try:
            print_menu(scripts, tests, last, last_time)
            choice = input("  Enter: ").strip()

            if choice in ("", "0", "exit", "q", "quit"):
                print("\n  Bye.\n")
                return 0

            if choice == "r" and last:
                _, last_time = run(py, last, root, [])
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
            for n, _, t in scripts + tests:
                if n == num:
                    last = t
                    _, last_time = run(py, t, root, extra)
                    found = True
                    break

            if not found:
                print(f"  ? No script #{num}")
                input("  Press Enter...")

        except EOFError:
            # Терминал закрыл поток ввода (таймаут, разрыв SSH, закрытие окна)
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
