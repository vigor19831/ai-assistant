#!/usr/bin/env python3
"""Run ruff linter and formatter over the entire project.

Respects exclude patterns in pyproject.toml (dev/, ops/, vendor/).
By default auto-fixes both lint issues and formatting.

Usage:
    python scripts/check_ruff.py            # auto-fix lint + format
    python scripts/check_ruff.py --check    # only check, no changes
"""

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

RUFF_TIMEOUT = 120  # seconds


def _quote_cmd(cmd: list[str]) -> str:
    """Quote command arguments for display."""
    return " ".join(shlex.quote(a) for a in cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ruff linter and formatter")
    parser.add_argument("--check", action="store_true", help="Only check, no auto-fix")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    src_path = project_root / "src"

    if not src_path.is_dir():
        print(f"ERROR: Source directory not found: {src_path}")
        return 1

    def _run(cmd: list[str], label: str) -> int:
        print(f"[{label}] Running: {_quote_cmd(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                cwd=project_root,
                timeout=RUFF_TIMEOUT,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 and "No module named ruff" in result.stderr:
                print("ERROR: 'ruff' not found. Install it: pip install ruff")
                return 1
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr and result.returncode != 0:
                print(result.stderr, end="", file=sys.stderr)
            return result.returncode
        except subprocess.TimeoutExpired:
            print(f"ERROR: {label} timed out after {RUFF_TIMEOUT} seconds")
            return 1
        except FileNotFoundError:
            print("ERROR: Python executable not found")
            return 1

    # 1. Lint
    lint_cmd = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--fix" if not args.check else "--no-fix",
        str(src_path),
    ]
    lint_code = _run(lint_cmd, "LINT")

    # 2. Format (always run, even if lint failed, to give full feedback)
    format_cmd = [sys.executable, "-m", "ruff", "format"]
    if args.check:
        format_cmd.append("--check")
    format_cmd.append(str(src_path))
    format_code = _run(format_cmd, "FORMAT")

    # Final status
    print()
    if lint_code == 0 and format_code == 0:
        print("=" * 50)
        print("ALL OK")
        print("=" * 50)
    else:
        print("=" * 50)
        if lint_code != 0 and format_code != 0:
            print("FAIL: Both lint and format failed")
        elif lint_code != 0:
            print("FAIL: Lint failed")
        else:
            print("FAIL: Format failed")
        print("=" * 50)

    return max(lint_code, format_code)


if __name__ == "__main__":
    sys.exit(main())
