#!/usr/bin/env python3
"""Run ruff linter and formatter – auto-fix by default (excludes .venv).

Usage:
    python scripts/check_ruff.py            # auto-fix lint + format
    python scripts/check_ruff.py --check    # only check, no auto-fix
    python scripts/check_ruff.py --watch    # additional ruff arguments
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_ruff(command: list[str], cwd: Path) -> int:
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd)
    return result.returncode


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent

    # Определяем режим: если есть --check, то только проверка
    args = sys.argv[1:]
    check_mode = "--check" in args
    # Убираем --check из аргументов, чтобы не передавать его ruff
    extra_args = [a for a in args if a != "--check"]

    exit_code = 0

    # 1. Lint
    lint_cmd = [sys.executable, "-m", "ruff", "check"]
    if check_mode:
        # просто проверка без исправлений
        lint_cmd.append("--check")
    else:
        lint_cmd.append("--fix")
    lint_cmd.append(str(project_root))
    lint_cmd.extend(extra_args)
    exit_code |= run_ruff(lint_cmd, project_root)

    # 2. Format
    format_cmd = [sys.executable, "-m", "ruff", "format"]
    if check_mode:
        format_cmd.append("--check")
    format_cmd.append(str(project_root))
    format_cmd.extend(extra_args)  # не все флаги подходят, но пусть пробрасывает
    exit_code |= run_ruff(format_cmd, project_root)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
