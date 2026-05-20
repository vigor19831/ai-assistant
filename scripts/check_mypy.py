#!/usr/bin/env python3
"""Run mypy static type checker for the project (excludes .venv).

Usage:
    python scripts/check_mypy.py                 # default check
    python scripts/check_mypy.py --strict        # additional mypy flags
    python scripts/check_mypy.py core/adapters   # check specific package
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent

    # Базовые исключения, чтобы не лезть в виртуальное окружение
    exclude_patterns = [
        ".venv",
        "venv",
        "__pycache__",
        "data",
        "logs",
        "tmp",
        "temp",
        "vendor",
        "scripts",
        "tests",  # tests проверяем отдельно через pytest
    ]
    exclude_str = "|".join(r"/" + p for p in exclude_patterns)

    cmd = [
        sys.executable,
        "-m",
        "mypy",
        str(project_root),
        "--exclude",
        exclude_str,
    ]

    # Проброс дополнительных аргументов (например, --strict, --config-file=...)
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
