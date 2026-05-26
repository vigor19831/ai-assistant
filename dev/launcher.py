#!/usr/bin/env python3
"""Launcher — two columns, green active marker, timestamps."""

from __future__ import annotations

import logging.handlers
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

# --- config ---------------------------------------------------------------

SCRIPT_ORDER = [
    "start",
    "stop",
    "clean_cache",
    "context_build",
    "index_documents",
    "terminal",
]
BACKGROUND = {"start"}
TEST_FLAGS = {
    "clean_cache": ["--clean"],
    "context_build": ["--full"],
    "download_tokenizers": ["--auto"],
}
TEST_MODES = {
    "default": [],
    "reverse": ["--reverse"],
    "forked": ["--forked"],
    "e2e": ["-m", "online"],
}

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

VENV_NAME = ".venv"
PYTHON_SUBPATH = "Scripts/python.exe" if os.name == "nt" else "bin/python"

_EXTRA_RE = re.compile(r"^[a-zA-Z0-9_.\-/:=@]+$")

TERMINAL_CMD: dict[str, Callable[[str, str], list[str]]] = {
    "nt": lambda venv, root: [
        "cmd",
        "/c",
        "start",
        "cmd",
        "/k",
        f"{venv}\\Scripts\\activate.bat && cd /d {root}",
    ],
    "darwin": lambda venv, root: [
        "osascript",
        "-e",
        f'tell application "Terminal" to do script "source {venv}/bin/activate && cd {root}"',
    ],
    "posix": lambda venv, root: [
        # Fallback chain: try common terminals
        "bash",
        "-c",
        f"for t in gnome-terminal konsole alacritty xterm; do "
        f'if command -v "$t" >/dev/null 2>&1; then '
        f'  exec "$t" -- bash -c "source {venv}/bin/activate && cd {root} && exec bash"; '
        f"fi; done; "
        f'echo "No supported terminal found" >&2; exit 1',
    ],
}

# --- helpers --------------------------------------------------------------


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def enable_ansi() -> None:
    """Включить ANSI-цвета в Windows-консоли."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
            mode.value |= 0x0004
            kernel32.SetConsoleMode(h_out, mode)
    except Exception:
        pass


def pad_ansi(text: str, width: int) -> str:
    plain = re.sub(r"\033\[[0-9;]*m", "", text)
    pad = width - len(plain)
    return text + " " * pad if pad > 0 else text


def get_python(root: Path) -> str:
    """Return the Python interpreter inside the project's virtual env.

    Never falls back to sys.executable — explicit isolation is mandatory.
    """
    exe = root / VENV_NAME / PYTHON_SUBPATH
    if not exe.exists():
        raise FileNotFoundError(
            f"Virtual-env interpreter not found: {exe}\n\n"
            f"Create it:  python -m venv {VENV_NAME}\n"
            f"Install:    {exe} -m pip install -e '.[dev,faiss]'"
        )
    if not os.access(exe, os.X_OK):
        raise PermissionError(
            f"Found interpreter is not executable: {exe}\nTry: chmod +x {exe}"
        )
    return str(exe)


def ensure_venv(root: Path) -> str:
    """Wrapper with clear UI error message."""
    try:
        return get_python(root)
    except (FileNotFoundError, PermissionError) as exc:
        print(f"\n{RED}❌ ENVIRONMENT ERROR{RESET}")
        print(f"{RED}   {exc}{RESET}\n")
        print(f"{YELLOW}Hint:{RESET} Run these commands from the project root:\n")
        print(f"   python -m venv {VENV_NAME}")
        print(f"   {VENV_NAME}/{PYTHON_SUBPATH} -m pip install -e '.[dev,faiss]'\n")
        sys.exit(1)


def collect(root: Path, subdir: str) -> list[Path]:
    d = root / subdir
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*.py") if p.is_file() and p.name != "__init__.py")


def sort_scripts(files: list[Path]) -> list[Path]:
    order = {name: i for i, name in enumerate(SCRIPT_ORDER)}

    def key(p: Path) -> tuple[int, str]:
        return (order.get(p.stem, 999), p.stem)

    return sorted(files, key=key)


def flag_hint(target: str) -> str:
    flags = TEST_FLAGS.get(Path(target).stem)
    return " ".join(flags) if flags else ""


def ask_flags(target: str) -> list[str]:
    flags = TEST_FLAGS.get(Path(target).stem)
    if not flags:
        return []
    try:
        ans = input(f"Add flags {' '.join(flags)}? [y/n]: ").strip().lower()
    except EOFError:
        return []
    return flags if ans in ("y", "yes") else []


def ask_test_mode() -> list[str]:
    """Ask user which test mode to run for 'RUN ALL TESTS'."""
    print(f"\n{YELLOW}Select test mode:{RESET}")
    print("  [1] default   — normal run (fast, shared process)")
    print("  [2] reverse   — reverse order (detects order dependencies)")
    print("  [3] forked    — isolated processes (slowest, 100% isolation)")
    print("  [4] e2e       — include online tests (requires running server)")
    try:
        ans = input("Mode [1]: ").strip()
    except EOFError:
        return []
    mapping = {"1": "default", "2": "reverse", "3": "forked", "4": "e2e"}
    mode = mapping.get(ans, "default")
    return TEST_MODES[mode]


def _sanitize_extra(extra: list[str]) -> list[str] | None:
    bad = [arg for arg in extra if not _EXTRA_RE.fullmatch(arg)]
    if bad:
        print(f"\n>>> {RED}Invalid extra arguments rejected: {bad}{RESET}")
        return None
    return extra


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
            n, label, target = scripts[i]
            star = f"{GREEN}*{RESET}" if n == last else " "
            bg = " [bg]" if Path(target).stem in BACKGROUND else ""
            left = f" [{n:2d}]{star} {label}{bg}"

        right = ""
        if i < len(tests):
            n, label, target = tests[i]
            star = f"{GREEN}*{RESET}" if n == last else " "
            hint = flag_hint(target)
            right = f" [{n:2d}]{star} {label}"
            if hint:
                right += f"  ({hint})"

        print(f"{pad_ansi(left, w)}    {right}")

    print("-" * total)
    print(" [r]  Rerun last")
    print(" [0]  Exit")
    print("=" * total)


def run(python, target, root, extra, mode_extra):
    ts = timestamp()
    if target.startswith("pytest:"):
        cmd = (
            [
                python,
                "-m",
                "pytest",
                target.split(":", 1)[1],
                "-v",
            ]
            + extra
            + mode_extra
        )
        print(f"\n>>> [{ts}] pytest tests")
        if mode_extra:
            mode_label = {
                "--reverse": "reverse",
                "--forked": "forked",
                "-m": "e2e",
            }.get(mode_extra[0], "custom")
            print(f">>> [{ts}] Mode: {mode_label}")
    else:
        cmd = [python, target] + extra
        print(f"\n>>> [{ts}] {Path(target).relative_to(root)}")
        if extra:
            print(f">>> [{ts}] (extra: {' '.join(extra)})")

    print(f">>> [{ts}] {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=root)

    # Color-coded exit status
    if res.returncode == 0:
        status = f"{GREEN}OK{RESET}"
    else:
        status = f"{RED}FAILED (exit {res.returncode}){RESET}"

    print(f"\n>>> [{timestamp()}] {status}")

    try:
        input(">>> Press Enter to return to menu... ")
    except EOFError:
        print(">>> (non-interactive, pausing 15s)")
        time.sleep(15)

    return res.returncode


def _get_rotating_log(log_file: Path) -> logging.handlers.RotatingFileHandler:
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    return handler


def run_bg(python, target, root, extra):
    target_path = Path(target)
    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)

    log_file = data_dir / f"{target_path.stem}.log"
    pid_file = data_dir / f"{target_path.stem}.pid"

    handler = _get_rotating_log(log_file)
    log_fp = handler.stream

    kwargs = {
        "cwd": root,
        "stdout": log_fp,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen([python, str(target_path)] + extra, **kwargs)

    pid_file.write_text(str(proc.pid), encoding="utf-8")

    ts = timestamp()
    print(f"\n>>> [{ts}] {GREEN}{target_path.name} running in background{RESET}")
    print(f">>> [{ts}] PID: {proc.pid}")
    print(f">>> [{ts}] Log: {log_file.relative_to(root)}")

    # Wait for server to be ready
    import urllib.request

    url = "http://127.0.0.1:8000/health"
    time.sleep(0.3)  # дать серверу фору
    for i in range(50):  # 50 попыток × 0.2с = 10 сек макс
        try:
            urllib.request.urlopen(url, timeout=0.5)
            print(f">>> [{ts}] {GREEN}Server ready at {url}{RESET}")
            break
        except Exception:
            time.sleep(0.2)
    else:
        print(
            f">>> [{ts}] {YELLOW}Server starting... "
            f"check {log_file.relative_to(root)}{RESET}"
        )

    return 0


def run_terminal(root: Path) -> int:
    """Open system terminal with activated venv."""
    venv = root / ".venv"
    if not venv.exists():
        print(f">>> {RED}No .venv found. Run setup first.{RESET}")
        return 1
    cmd_factory = TERMINAL_CMD.get(os.name, TERMINAL_CMD["posix"])
    cmd = cmd_factory(str(venv), str(root))
    ts = timestamp()
    print(f"\n>>> [{ts}] Opening terminal with .venv")
    print(f">>> [{ts}] {' '.join(cmd)}")
    subprocess.Popen(cmd)
    return 0


def find_target(num, scripts, tests):
    for n, label, target in scripts + tests:
        if n == num:
            return label, target
    return None, None


def main() -> int:
    enable_ansi()

    root = Path(__file__).parent.parent.resolve()
    py = ensure_venv(root)

    script_files = sort_scripts(
        collect(root, "ops/scripts") + collect(root, "dev/scripts")
    )
    test_files = collect(root, "dev/tests")

    scripts = []
    tests = []
    n = 1

    for f in script_files:
        scripts.append((n, f.name, str(f)))
        n += 1

    # Terminal launcher
    scripts.append((n, "TERMINAL (.venv)", "__terminal__"))
    n += 1

    if test_files:
        tests.append((n, "RUN ALL TESTS", f"pytest:{root / 'dev/tests'}"))
        n += 1
        for f in test_files:
            tests.append((n, f.name, str(f)))
            n += 1

    if not scripts and not tests:
        print("Nothing to run.")
        return 1

    last_num = None
    last_target = None
    last_extra = []
    last_mode_extra: list[str] = []

    while True:
        print_menu(scripts, tests, last_num)

        try:
            choice = input("\nEnter number: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not choice or choice in ("0", "exit", "quit"):
            print("Bye.")
            return 0

        if choice.lower() == "r":
            if last_target:
                if Path(last_target).stem in BACKGROUND and not last_target.startswith(
                    "pytest:"
                ):
                    run_bg(py, last_target, root, last_extra)
                else:
                    run(py, last_target, root, last_extra, last_mode_extra)
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

        if not target.startswith("pytest:") and not extra:
            extra = ask_flags(target)

        # Для "RUN ALL TESTS" спрашиваем режим
        mode_extra: list[str] = []
        if target.startswith("pytest:"):
            test_path = Path(target.split(":", 1)[1])
            if test_path.name == "tests" and test_path.parent.name == "dev":
                mode_extra = ask_test_mode()

        sanitized = _sanitize_extra(extra)
        if sanitized is None:
            continue
        extra = sanitized

        if target == "__terminal__":
            run_terminal(root)
            continue

        last_num, last_target, last_extra = num, target, extra
        last_mode_extra = mode_extra

        if Path(target).stem in BACKGROUND and not target.startswith("pytest:"):
            run_bg(py, target, root, extra)
        else:
            run(py, target, root, extra, mode_extra)


if __name__ == "__main__":
    sys.exit(main())
