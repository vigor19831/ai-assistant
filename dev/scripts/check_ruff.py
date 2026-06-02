#!/usr/bin/env python3
"""Run ruff linter and formatter over the entire project.

Respects exclude patterns in pyproject.toml (dev/, ops/, vendor/).
By default auto-fixes both lint issues and formatting.

Usage:
    python dev/scripts/check_ruff.py            # auto-fix lint + format
    python dev/scripts/check_ruff.py --check    # only check, no changes
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ruff linter and formatter")
    parser.add_argument("--check", action="store_true", help="Only check, no auto-fix")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    src_path = project_root / "src"

    if not src_path.is_dir():
        print(f"ERROR: Source directory not found: {src_path}")
        return 1

    exit_code = 0

    def _run(cmd: list[str]) -> int:
        print(f"Running: {' '.join(cmd)}")
        try:
            return subprocess.run(cmd, cwd=project_root).returncode
        except FileNotFoundError:
            print("ERROR: 'ruff' not found. Install it: pip install ruff")
            return 1

    # 1. Lint (src/ only, not entire project_root)
    lint_cmd = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--fix" if not args.check else "--no-fix",
        str(src_path),
    ]
    exit_code = max(exit_code, _run(lint_cmd))

    # 2. Format (src/ only)
    format_cmd = [sys.executable, "-m", "ruff", "format"]
    if args.check:
        format_cmd.append("--check")
    format_cmd.append(str(src_path))
    exit_code = max(exit_code, _run(format_cmd))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
