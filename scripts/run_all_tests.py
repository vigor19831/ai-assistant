#!/usr/bin/env python3
"""Run all tests with mode selection and logging."""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"

MODES = {
    "1": ([], "default — normal run"),
    "2": (["-m", "online"], "e2e — include online tests"),
    "3": (["--cov=src/ai_assistant", "--cov-report=term-missing"], "coverage — with coverage report"),
}


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def main() -> int:
    if not TESTS_DIR.exists():
        print(f"Tests directory not found: {TESTS_DIR}")
        return 1

    print("Select test mode:")
    for k, (_, desc) in MODES.items():
        print(f"  [{k}] {desc}")

    try:
        ans = input("Mode [1]: ").strip()
    except EOFError:
        ans = "1"

    flags, _ = MODES.get(ans, MODES["1"])

    cmd = [sys.executable, "-m", "pytest", str(TESTS_DIR), "-v", "--tb=long",
           "--color=yes", "--showlocals"] + flags

    log_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = ROOT / f"tests_run_{log_ts}.log"

    print(f"\n>>> Running: {' '.join(cmd)}")
    print(f">>> Log: {log_path}\n")

    with open(log_path, "w", encoding="utf-8") as log_fp:
        log_fp.write(f"=== Test run {log_ts} ===\n")
        log_fp.write(f"Command: {' '.join(cmd)}\n\n")

        res = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        log_fp.write(res.stdout)
        log_fp.write(f"\n\nExit code: {res.returncode}\n")

    lines = res.stdout.strip().splitlines()
    summary = next((l for l in reversed(lines) if l.startswith("=") or "passed" in l or "failed" in l), "")
    clean_summary = _strip_ansi(summary).strip("=").strip()

    print("=" * 50)
    if res.returncode == 0:
        print("  [ OK ] ALL TESTS PASSED")
    else:
        print("  [FAIL] TESTS FAILED")
    print("=" * 50)
    if clean_summary:
        print(f"  {clean_summary}")
    print(f"\n  Full log: {log_path}")

    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
