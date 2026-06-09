#!/usr/bin/env python3
"""Launcher — scan scripts/ & tests/, show two-column menu, run by number."""

import argparse
import contextlib
import os
import subprocess
import sys
from pathlib import Path

VENV_NAME = ".venv"
PYTHON_SUBPATH = "Scripts/python.exe" if os.name == "nt" else "bin/python"

SCRIPT_ORDER = ["start", "stop"]


def get_python(root: Path) -> str:
    exe = root / VENV_NAME / PYTHON_SUBPATH
    if not exe.exists():
        raise FileNotFoundError(
            f"Virtual-env interpreter not found: {exe}\n\n"
            f"Create it:  python -m venv {VENV_NAME}\n"
            f"Install:    {exe} -m pip install -e '.[dev,faiss]'"
        )
    return str(exe)


def collect(root: Path, subdir: str) -> list[Path]:
    d = root / subdir
    if not d.is_dir():
        return []
    return sorted(
        p for p in d.rglob("*.py")
        if p.is_file() and p.name != "__init__.py"
    )


def sort_scripts(files: list[Path]) -> list[Path]:
    order = {name: i for i, name in enumerate(SCRIPT_ORDER)}

    def key(p: Path) -> tuple[int, str]:
        return (order.get(p.stem, 999), p.stem)

    return sorted(files, key=key)


def print_menu(scripts, tests, last):
    w = 38
    rows = max(len(scripts), len(tests))
    total = w * 2 + 4

    print("\n" + "=" * total)
    print(f"{'SCRIPTS':^{w}}    {'TESTS':^{w}}")
    print("-" * total)

    for i in range(rows):
        left = ""
        if i < len(scripts):
            n, label, _ = scripts[i]
            star = " *" if n == last else ""
            left = f" [{n:2d}]{star} {label}"

        right = ""
        if i < len(tests):
            n, label, _ = tests[i]
            star = " *" if n == last else ""
            right = f" [{n:2d}]{star} {label}"

        print(f"{left:<{w}}    {right}")

    print("-" * total)
    print(" [r]  Rerun last")
    print(" [0]  Exit")
    print("=" * total)


def run(python, target, root, extra):
    cmd = [python, target] + extra
    print(f"\n>>> {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=root)
    with contextlib.suppress(EOFError):
        input("\n>>> Press Enter to return to menu... ")
    return res.returncode


def find_target(num, scripts, tests):
    for n, label, target in scripts + tests:
        if n == num:
            return label, target
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Assistant Launcher")
    parser.add_argument("--no-menu", action="store_true", help="Non-interactive mode")
    parser.add_argument("target", nargs="?", help="Number or 'r'")
    parser.add_argument("extra", nargs=argparse.REMAINDER, help="Extra arguments")
    args = parser.parse_args()

    root = Path(__file__).parent.resolve()
    py = get_python(root)

    script_files = sort_scripts(collect(root, "scripts"))
    test_files = collect(root, "tests")

    scripts = []
    tests = []
    n = 1

    for f in script_files:
        scripts.append((n, f.name, str(f)))
        n += 1

    for f in test_files:
        tests.append((n, f.name, str(f)))
        n += 1

    last_num = None
    last_target = None
    last_extra = []

    # --- non-interactive mode ---
    if args.no_menu:
        target_str = args.target or ""
        extra = [e for e in args.extra if e != "--"]

        if target_str.lower() == "r":
            print("No previous run.")
            return 1

        # 0 — exit in non-interactive mode too
        if target_str == "0":
            print("Bye.")
            return 0

        try:
            num = int(target_str)
        except ValueError:
            print(f"Invalid target: {target_str}")
            return 1

        label, target = find_target(num, scripts, tests)
        if target is None:
            print("Number not found.")
            return 1

        return run(py, target, root, extra)

    # --- interactive mode ---
    while True:
        print_menu(scripts, tests, last_num)

        try:
            choice = input("\nEnter number: ").strip()
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
            print("Invalid input.")
            continue

        extra = parts[1].split() if len(parts) > 1 else []
        label, target = find_target(num, scripts, tests)
        if target is None:
            print("Number not found.")
            continue

        last_num, last_target, last_extra = num, target, extra
        run(py, target, root, extra)


if __name__ == "__main__":
    sys.exit(main())
