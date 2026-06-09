#!/usr/bin/env python3
"""Run mypy static type checker for the project (src/ only, tests excluded).

Checks the main source tree (src/ai_assistant/).
Tests (tests/) are excluded by pyproject.toml and not passed to mypy,
avoiding false positives from untyped test fixtures.

Usage:
    python scripts/check_mypy.py                 # default check
    python scripts/check_mypy.py --strict        # additional mypy flags
    python scripts/check_mypy.py ai_assistant/core/adapters   # check specific package
"""

import subprocess
import sys
from pathlib import Path


MYPY_TIMEOUT = 300  # seconds


def _quote_cmd(cmd: list[str]) -> str:
    """Quote command arguments for display."""
    return " ".join(
        f'"{a}"' if " " in a or '"' in a or "'" in a else a for a in cmd
    )


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent  # scripts/ → root
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

    print(f"Running: {_quote_cmd(cmd)}")
    print(f"Working directory: {project_root}")

    try:
        result = subprocess.run(cmd, cwd=project_root, timeout=MYPY_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"ERROR: mypy timed out after {MYPY_TIMEOUT} seconds")
        return 1
    except FileNotFoundError:
        print("ERROR: Python executable not found")
        return 1

    if result.returncode != 0 and "No module named mypy" in (result.stderr or ""):
        print("ERROR: 'mypy' not found. Install it: pip install mypy")
        return 1

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
