#!/usr/bin/env python3
"""Run helper scripts from scripts/ and tests/. Invoke from project root: python run_scripts.py"""

import os
import subprocess
import sys
from pathlib import Path

VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"

# Auto-activate venv
_venv = Path(__file__).parent / ".venv"
_venv_py = _venv / PY
if _venv.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    os.execl(str(_venv_py), str(_venv_py), *sys.argv)


def get_python(root: Path) -> str:
    return str(root / VENV / PY)


def collect(root: Path, subdir: str) -> list[Path]:
    d = root / subdir
    return sorted(p for p in d.glob("*.py") if p.name != "__init__.py")


def _sort(files: list[Path]) -> list[Path]:
    return sorted(files, key=lambda p: p.name)


def print_menu(items, last):
    w = 38
    print("\n" + "=" * (w + 4))
    print(f"{'MENU':^{w}}")
    print("-" * (w + 4))
    for n, name, _ in items:
        mark = "*" if n == last else " "
        print(f" [{n:2d}] {mark} {name}")
    print("-" * (w + 4))
    print(" [r]  Rerun last")
    print(" [0]  Exit")
    print("=" * (w + 4))


def run(py, target, root, extra):
    cmd = [py, target] + extra
    print(f"\n>>> {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=root)
    input("\n>>> Press Enter... ")
    return res.returncode


def main():
    root = Path(__file__).parent.resolve()
    py = get_python(root)

    scripts = [(i + 1, f.name, str(f)) for i, f in enumerate(_sort(collect(root, "scripts")))]
    tests = [(i + len(scripts) + 1, f.name, str(f)) for i, f in enumerate(_sort(collect(root, "tests")))]
    items = scripts + tests

    last = None
    while True:
        print_menu(items, last)
        choice = input("\nEnter: ").strip()

        if choice in ("", "0", "exit"):
            print("\nBye.")
            return 0
        if choice == "r" and last:
            run(py, last, root, [])
            continue

        try:
            num = int(choice.split()[0])
        except ValueError:
            continue

        extra = choice.split()[1:] if len(choice.split()) > 1 else []
        for n, _, t in items:
            if n == num:
                last = t
                run(py, t, root, extra)
                break


if __name__ == "__main__":
    sys.exit(main())
