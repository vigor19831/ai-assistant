#!/usr/bin/env python3
"""Run vulture dead code checker for the project.

Usage:
    python dev/scripts/check_vulture.py              # default check (70% confidence)
    python dev/scripts/check_vulture.py --min-confidence 80  # stricter
    python dev/scripts/check_vulture.py --exclude tests,scripts  # custom exclude
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# ── Absolute project root ──
SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent

# ── Find ai_assistant package ──
if (PROJECT_ROOT / "ai_assistant").exists():
    AI_ROOT = PROJECT_ROOT / "ai_assistant"
elif (PROJECT_ROOT / "src" / "ai_assistant").exists():
    AI_ROOT = PROJECT_ROOT / "src" / "ai_assistant"
elif (PROJECT_ROOT.parent / "src" / "ai_assistant").exists():
    AI_ROOT = PROJECT_ROOT.parent / "src" / "ai_assistant"
else:
    AI_ROOT = PROJECT_ROOT.parent / "ai_assistant"

DEFAULT_PATHS = [
    str(AI_ROOT / "core"),
    str(AI_ROOT / "adapters"),
    str(AI_ROOT / "features"),
    str(AI_ROOT / "api"),
    str(AI_ROOT / "pipeline"),
]

DEFAULT_EXCLUDE = [
    ".venv",
    "venv",
    "__pycache__",
    "tests",
    "scripts",
    "data",
    "logs",
    "tmp",
    "temp",
    "vendor",
    "ui",
]

DEFAULT_IGNORE_NAMES = [
    "handler",
    "entry",
    "user_id",
    "entry_id",
    "session_id",
    "event",
    "details",
    "token",
]


def run_vulture(
    paths: list[str],
    exclude: list[str],
    min_confidence: int,
    sort_by_size: bool,
    ignore_names: list[str],
) -> int:
    """Execute vulture with given parameters."""
    # Filter out non-existent directories
    existing_paths = [p for p in paths if Path(p).exists()]
    missing = [p for p in paths if not Path(p).exists()]

    for m in missing:
        print(f"Warning: skipping missing directory: {m}")

    if not existing_paths:
        print("Error: no valid directories to check")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "vulture",
    ]

    cmd.extend(existing_paths)

    if exclude:
        cmd.extend(["--exclude", ",".join(exclude)])

    cmd.extend(["--min-confidence", str(min_confidence)])

    if sort_by_size:
        cmd.append("--sort-by-size")

    if ignore_names:
        cmd.extend(["--ignore-names", ",".join(ignore_names)])

    print(f"Running: {' '.join(cmd)}")
    print(f"Project root: {PROJECT_ROOT}")
    print("-" * 55)

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dead code checker — vulture wrapper",
    )
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=70,
        help="Minimum confidence level (0-100). Default: 70",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=",".join(DEFAULT_EXCLUDE),
        help=(
            f"Comma-separated exclude patterns. Default: {','.join(DEFAULT_EXCLUDE)}"
        ),
    )
    parser.add_argument(
        "--ignore-names",
        type=str,
        default=",".join(DEFAULT_IGNORE_NAMES),
        help=(
            "Comma-separated names to ignore. "
            f"Default: {','.join(DEFAULT_IGNORE_NAMES)}"
        ),
    )
    parser.add_argument(
        "--no-sort-by-size",
        action="store_true",
        help="Disable sort-by-size output",
    )
    parser.add_argument(
        "--no-ignore-defaults",
        action="store_true",
        help="Disable default ignore-names",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Custom paths to check (default: core, adapters, features, api, pipeline)",
    )

    args = parser.parse_args()

    paths = args.paths if args.paths else DEFAULT_PATHS
    exclude = [e.strip() for e in args.exclude.split(",") if e.strip()]

    if args.no_ignore_defaults:
        ignore_names = []
    else:
        ignore_names = [n.strip() for n in args.ignore_names.split(",") if n.strip()]

    return run_vulture(
        paths=paths,
        exclude=exclude,
        min_confidence=args.min_confidence,
        sort_by_size=not args.no_sort_by_size,
        ignore_names=ignore_names,
    )


if __name__ == "__main__":
    sys.exit(main())
