#!/usr/bin/env python3
"""Run mypy static type checker for the project.

Usage:
    python dev/scripts/check_mypy.py                 # default check
    python dev/scripts/check_mypy.py --strict        # additional mypy flags
    python dev/scripts/check_mypy.py core/adapters   # check specific package
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    src_path = Path(__file__).resolve().parent.parent.parent / "src"
    if not src_path.exists():
        print(f"ERROR: Source path not found: {src_path}")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "mypy",
        str(src_path),
    ]

    # Проброс дополнительных аргументов
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
