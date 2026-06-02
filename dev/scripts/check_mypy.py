#!/usr/bin/env python3
"""Run mypy static type checker for the project (src/ only, tests excluded).

Checks the main source tree (src/ai_assistant/).
Tests (dev/tests/) are excluded by pyproject.toml and not passed to mypy,
avoiding false positives from untyped test fixtures.

Usage:
    python dev/scripts/check_mypy.py                 # default check
    python dev/scripts/check_mypy.py --strict        # additional mypy flags
    python dev/scripts/check_mypy.py ai_assistant/core/adapters   # check specific package
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent  # dev/scripts/ → dev/ → root
    src_path = project_root / "src"

    if not src_path.is_dir():
        print(f"ERROR: Source directory not found: {src_path}")
        return 1

    # Separate flags from paths
    args = sys.argv[1:]
    flags = [a for a in args if a.startswith("-")]
    paths = [a for a in args if not a.startswith("-")]

    # Resolve targets: if user gives paths, auto-prefix with src/ when relative
    targets: list[str] = []
    for p in paths:
        p_path = Path(p)
        if not p_path.is_absolute():
            candidate = project_root / p
            if not candidate.exists():
                candidate = src_path / p
            p = str(candidate)
        targets.append(p)

    if not targets:
        targets = [str(src_path)]

    cmd = [
        sys.executable,
        "-m",
        "mypy",
        *flags,
        *targets,
    ]

    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {project_root}")

    try:
        result = subprocess.run(cmd, cwd=project_root)
    except FileNotFoundError:
        print("ERROR: 'mypy' not found. Install it: pip install mypy")
        return 1

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
