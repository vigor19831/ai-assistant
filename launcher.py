#!/usr/bin/env python3
"""Launcher — menu for scripts/ and tests/. Run from project root: python launcher.py"""

import os
import subprocess
import sys
from pathlib import Path

VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"

# Auto-activate venv if running from outside
_VENV = Path(__file__).parent / ".venv"
_VENV_PY = _VENV / PY

if _VENV.exists() and not sys.executable.startswith(str(_VENV)):
    os.execl(str(_VENV_PY), str(_VENV_PY), *sys.argv)


def get_python(root: Path) -> str:
    exe = root / VENV / PY
    if not exe.exists():
        raise FileNotFoundError(f"No venv: {exe}")
    return str(exe)


def collect(root: Path, subdir: str) -> list[Path]:
    d = root / subdir
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*.py") if p.is_file() and p.name != "__init__.py")


def print_menu(scripts, tests, last):
    w = 38
    rows = max(len(scripts), len(tests))
    total = w * 2 + 4

    print("\n" + "=" * total)
    print(f"{'SCRIPTS':^{w}}    {'TESTS':^{w}}")
    print("-" * total)

    for i in range(rows):
        left = f" [{scripts[i][0]:2d}] {'*' if scripts[i][0] == last else ' '} {scripts[i][1]}" if i < len(scripts) else ""
        right = f" [{tests[i][0]:2d}] {'*' if tests[i][0] == last else ' '} {tests[i][1]}" if i < len(tests) else ""
        print(f"{left:<{w}}    {right}")

    print("-" * total)
    print(" [r]  Rerun last")
    print(" [0]  Exit")
    print("=" * total)


def run(py, target, root, extra):
    cmd = [py, target] + extra
    print(f"\n>>> {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=root)
    input("\n>>> Press Enter to return to menu... ")
    return res.returncode


def main():
    # Root is the directory where launcher.py lives (project root)
    root = Path(__file__).parent.resolve()
    py = get_python(root)

    scripts, tests, n = [], [], 1
    for f in collect(root, "scripts"):
        if f.name != "__init__.py":
            scripts.append((n, f.name, str(f)))
            n += 1
    for f in collect(root, "tests"):
        tests.append((n, f.name, str(f)))
        n += 1

    last_num, last_target, last_extra = None, None, []

    while True:
        print_menu(scripts, tests, last_num)

        try:
            choice = input("\nEnter: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not choice:
            continue
        if choice in ("0", "exit", "quit"):
            print("\nBye.")
            return 0

        if choice.lower() == "r":
            if last_target:
                run(py, last_target, root, last_extra)
            else:
                print("No previous run.")
            continue

        parts = choice.split(maxsplit=1)
        try:
            num = int(parts[0])
        except ValueError:
            print("Invalid.")
            continue

        extra = parts[1].split() if len(parts) > 1 else []
        target = None
        for n, label, t in scripts + tests:
            if n == num:
                target = t
                break

        if target is None:
            print("Not found.")
            continue

        last_num, last_target, last_extra = num, target, extra
        run(py, target, root, extra)


if __name__ == "__main__":
    sys.exit(main())
