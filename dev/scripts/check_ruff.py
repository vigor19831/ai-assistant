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

    exit_code = 0

    # 1. Lint
    lint_cmd = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--fix" if not args.check else "--no-fix",
        str(project_root),
    ]
    print(f"Running: {' '.join(lint_cmd)}")
    result = subprocess.run(lint_cmd, cwd=project_root)
    exit_code |= result.returncode

    # 2. Format
    format_cmd = [sys.executable, "-m", "ruff", "format"]
    if args.check:
        format_cmd.append("--check")
    format_cmd.append(str(project_root))
    print(f"Running: {' '.join(format_cmd)}")
    result = subprocess.run(format_cmd, cwd=project_root)
    exit_code |= result.returncode

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
