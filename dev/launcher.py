#!/usr/bin/env python3
"""Launcher — two columns, green active marker, timestamps, auto-logs, double-Enter exit."""

from __future__ import annotations

import argparse
import os
import re
import socket
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
    "clean_cache": ["--clean", "--yes"],
    "download_tokenizers": ["--auto"],
}
# context_build has its own ask function, not in TEST_FLAGS
TEST_MODES = {
    "default": [],
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
        "bash",
        "-c",
        f"for t in gnome-terminal konsole alacritty xterm; do "
        f'if command -v "$t" >/dev/null 2>&1; then '
        f'  "$t" -- bash -c "source {venv}/bin/activate && cd {root} && exec bash"; '
        f"  break; "
        f"fi; done; "
        f'echo "No supported terminal found" >&2; exit 1',
    ],
}

# --- helpers --------------------------------------------------------------


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def enable_ansi() -> None:
    """Enable ANSI colors in Windows console."""
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
    """Return the Python interpreter inside the project's virtual env."""
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


def ask_context_build_mode() -> list[str]:
    """Ask user which context build mode to use."""
    print(f"\n{YELLOW}Select context build mode:{RESET}")
    print("  [1] super    — rules + signatures only (~20 KB, daily use)")
    print("  [2] compact  — critical code + signatures + inventory (~200 KB)")
    print("  [3] full     — absolute everything (~800 KB, audit only)")
    try:
        ans = input("Mode [1]: ").strip()
    except EOFError:
        return ["--super"]
    mapping = {"1": "--super", "2": "--compact", "3": "--full"}
    return [mapping.get(ans, "--super")]


def ask_flags(target: str) -> list[str]:
    stem = Path(target).stem
    if stem == "context_build":
        return ask_context_build_mode()
    flags = TEST_FLAGS.get(stem)
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
    print("  [2] e2e       — include online tests (requires running server)")
    try:
        ans = input("Mode [1]: ").strip()
    except EOFError:
        return []
    mapping = {"1": "default", "2": "e2e"}
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


# --- run ------------------------------------------------------------------


def run(python, target, root, extra, mode_extra):
    ts = timestamp()
    if target.startswith("pytest:"):
        test_path = target.split(":", 1)[1]
        cmd = (
            [
                python,
                "-m",
                "pytest",
                test_path,
                "-v",
                "--tb=long",
                "--color=yes",
                "--showlocals",
                "--capture=tee-sys",
            ]
            + extra
            + mode_extra
        )
        print(f"\n>>> [{ts}] pytest tests")
        if mode_extra:
            mode_label = {
                "-m": "e2e",
            }.get(mode_extra[0], "default")
            print(f">>> [{ts}] Mode: {mode_label}")

        # --- auto-log to dev/ with full traceback ---
        log_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = root / "dev" / f"tests_run_{log_ts}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        print(f">>> [{ts}] Logging to: {log_path.relative_to(root)}")
        print(f">>> [{ts}] {' '.join(cmd)}")

        with open(log_path, "w", encoding="utf-8") as log_fp:
            log_fp.write(f"=== Test run {log_ts} ===\n")
            log_fp.write(f"Command: {' '.join(cmd)}\n\n")
            log_fp.flush()

            proc = subprocess.Popen(
                cmd,
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
            )

            # Parse pytest output in real-time
            failed_tests = []  # Full names for file
            failed_by_class = {}  # For terminal: class -> count
            passed = failed = skipped = 0

            for line in proc.stdout:
                # Strip color codes for file, keep for terminal if needed
                clean_line = re.sub(r"\033\[[0-9;]*m", "", line).rstrip()

                # Count results
                if " PASSED " in clean_line:
                    passed += 1
                elif " FAILED " in clean_line:
                    failed += 1
                    # Extract: "dev/tests/foo.py::TestClass::test_method FAILED"
                    match = re.search(r"([\w/\\]+\.py::[\w:]+)", clean_line)
                    if match:
                        full_name = match.group(1)
                        failed_tests.append(full_name)

                        # Group by class for terminal
                        parts = full_name.split("::")
                        if len(parts) >= 3:
                            class_name = parts[1]  # TestClass::test_method
                        elif len(parts) == 2:
                            class_name = parts[1] + " (fn)"  # module::test_function
                        else:
                            class_name = parts[0]  # fallback to filename
                        failed_by_class[class_name] = (
                            failed_by_class.get(class_name, 0) + 1
                        )
                elif " SKIPPED " in clean_line:
                    skipped += 1
                elif " XFAIL " in clean_line or " XPASS " in clean_line:
                    pass  # Ignore for now

                # Write to file with timestamp
                file_ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                log_fp.write(f"[{file_ts}] {clean_line}\n")
                log_fp.flush()

            proc.wait()
            res_returncode = proc.returncode

            # Write summary to file
            log_fp.write(f"\n{'=' * 60}\n")
            log_fp.write(
                f"SUMMARY: {passed} passed, {failed} failed, {skipped} skipped\n"
            )
            if failed_tests:
                log_fp.write(f"\nFAILED TESTS ({len(failed_tests)}):\n")
                for ft in failed_tests:
                    log_fp.write(f"  - {ft}\n")
            log_fp.write(f"{'=' * 60}\n")

        # Terminal output: brief summary only
        total = passed + failed + skipped
        print(
            f"\n>>> [{timestamp()}] {total} tests: {passed} passed, {failed} failed, {skipped} skipped"
        )

        if failed_by_class:
            # Sort by count descending
            sorted_classes = sorted(
                failed_by_class.items(), key=lambda x: x[1], reverse=True
            )
            class_strs = [f"{cls} ({cnt})" for cls, cnt in sorted_classes]

            print(f">>> [{timestamp()}] {RED}FAILED by class:{RESET}")
            # Print in groups of ~50 chars, wrapped
            line_parts = []
            current_len = 0
            for cs in class_strs:
                if current_len + len(cs) > 50 and line_parts:
                    print(f">>> [{timestamp()}]   {RED}{', '.join(line_parts)}{RESET}")
                    line_parts = [cs]
                    current_len = len(cs)
                else:
                    line_parts.append(cs)
                    current_len += len(cs) + 2
            if line_parts:
                print(f">>> [{timestamp()}]   {RED}{', '.join(line_parts)}{RESET}")

            # One example of specific test
            if failed_tests:
                print(f">>> [{timestamp()}] Example: {failed_tests[0]}")

        status = (
            f"{GREEN}OK{RESET}"
            if res_returncode == 0
            else f"{RED}FAILED (exit {res_returncode}){RESET}"
        )
        print(f">>> [{timestamp()}] {status}")
        print(f">>> [{timestamp()}] Full log saved: {log_path.relative_to(root)}")

    else:
        cmd = [python, target] + extra
        print(f"\n>>> [{ts}] {Path(target).relative_to(root)}")
        if extra:
            print(f">>> [{ts}] (extra: {' '.join(extra)})")
        print(f">>> [{ts}] {' '.join(cmd)}\n")

        res = subprocess.run(cmd, cwd=root, stdin=subprocess.DEVNULL)
        res_returncode = res.returncode

        status = (
            f"{GREEN}OK{RESET}"
            if res_returncode == 0
            else f"{RED}FAILED (exit {res_returncode}){RESET}"
        )
        print(f"\n>>> [{timestamp()}] {status}")

    try:
        input(">>> Press Enter to return to menu... ")
    except EOFError:
        pass

    return res_returncode


def _get_server_port(root: Path) -> int:
    """Read server port from config.yaml, fallback to 8000."""
    try:
        from ai_assistant.core.config import load_config
        cfg = load_config(str(root / "config.yaml"))
        return getattr(cfg, "port", 8000)
    except Exception:
        return 8000


def run_bg(python, target, root, extra):
    """Background launch: no PID files, no rotating logs. Just health-check + status."""
    target_path = Path(target)
    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)

    log_file = data_dir / f"{target_path.stem}.log"

    kwargs = {
        "cwd": root,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    # Open log file, run process, close log file promptly
    with open(log_file, "a", encoding="utf-8") as log_fp:
        kwargs["stdout"] = log_fp
        kwargs["stderr"] = subprocess.STDOUT
        proc = subprocess.Popen([python, str(target_path)] + extra, **kwargs)

    ts = timestamp()
    print(f"\n>>> [{ts}] {GREEN}{target_path.name} running in background{RESET}")
    print(f">>> [{ts}] PID: {proc.pid}")
    print(f">>> [{ts}] Log: {log_file.relative_to(root)}")

    # Wait for server to be ready
    port = _get_server_port(root)
    time.sleep(0.3)
    for _ in range(50):
        sock = None
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            print(
                f">>> [{ts}] {GREEN}Server ready at http://127.0.0.1:{port}/health{RESET}"
            )
            break
        except (OSError, ConnectionRefusedError, TimeoutError):
            time.sleep(0.2)
        finally:
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
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


def _shutdown(root: Path, python: str, scripts: list, tests: list) -> int:
    """Exit handler: stop server gracefully via stop.py if available."""
    # Find stop.py
    stop_target = None
    for _, _, target in scripts + tests:
        if Path(target).stem == "stop":
            stop_target = target
            break

    if stop_target:
        print(f"\n{YELLOW}>>> Stopping server...{RESET}")
        res = subprocess.run([python, stop_target], cwd=root)
        if res.returncode == 0:
            print(f"{GREEN}>>> Server stopped.{RESET}")
        else:
            print(f"{RED}>>> Stop script exited with code {res.returncode}.{RESET}")
    else:
        # Fallback: try to kill by PID file
        pid_file = root / "data" / "server.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
                else:
                    os.kill(pid, 15)  # SIGTERM
                print(f"{YELLOW}>>> Sent SIGTERM to PID {pid}.{RESET}")
            except (ValueError, OSError, ProcessLookupError) as e:
                print(f"{RED}>>> Could not stop server: {e}{RESET}")
        else:
            print(f"{YELLOW}>>> No stop script or PID file found.{RESET}")

    print("\nBye.")
    return 0


# --- main -----------------------------------------------------------------


def main() -> int:
    enable_ansi()

    parser = argparse.ArgumentParser(description="AI Assistant Launcher")
    parser.add_argument(
        "--no-menu", action="store_true", help="Non-interactive mode (CI)"
    )
    parser.add_argument("target", nargs="?", help="Number, 'r', or script name")
    parser.add_argument(
        "extra", nargs=argparse.REMAINDER, help="Extra arguments after --"
    )
    args = parser.parse_args()

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

    # --- non-interactive mode ------------------------------------------------
    if args.no_menu:
        target_str = args.target or ""
        extra_raw = [e for e in args.extra if e != "--"]

        if target_str.lower() == "r":
            print("No previous run.")
            return 1

        # Try to resolve by number
        try:
            num = int(target_str)
        except ValueError:
            print(f"Invalid target: {target_str}")
            return 1

        label, target = find_target(num, scripts, tests)
        if target is None:
            print("Number not found.")
            return 1

        sanitized = _sanitize_extra(extra_raw)
        if sanitized is None:
            return 1

        mode_extra: list[str] = []
        # In non-interactive mode, use default modes

        if target == "__terminal__":
            return run_terminal(root)

        if Path(target).stem in BACKGROUND and not target.startswith("pytest:"):
            return run_bg(py, target, root, sanitized)
        else:
            return run(py, target, root, sanitized, mode_extra)

    # --- interactive mode ----------------------------------------------------
    while True:
        print_menu(scripts, tests, last_num)

        try:
            choice = input("\nEnter number: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return _shutdown(root, py, scripts, tests)

        if not choice:
            continue

        if choice in ("0", "exit", "quit"):
            return _shutdown(root, py, scripts, tests)

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
