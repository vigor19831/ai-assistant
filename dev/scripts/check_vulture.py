#!/usr/bin/env python3
"""Run vulture dead code checker for the project (src/ only).

Scans the main source tree (src/ai_assistant/) for unused code.
Respects pyproject.toml conventions but does not parse it.
Paths are computed from script location, so no package installation is required.

Usage:
    python dev/scripts/check_vulture.py              # default check (70% confidence)
    python dev/scripts/check_vulture.py --min-confidence 80  # stricter
    python dev/scripts/check_vulture.py --exclude tests,scripts  # custom exclude
"""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


def _vulture_available() -> bool:
    """Check if vulture is installed."""
    return importlib.util.find_spec("vulture") is not None


def _default_source_paths() -> list[str]:
    """Return absolute paths to source subpackages under src/ai_assistant."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    src = project_root / "src" / "ai_assistant"
    subdirs = ["core", "adapters", "features", "api", "pipeline"]
    return [str(src / d) for d in subdirs if (src / d).exists()]


def main() -> int:
    if not _vulture_available():
        print("vulture is not installed. Install: pip install vulture")
        return 0

    parser = argparse.ArgumentParser(description="Dead code checker — vulture wrapper")
    parser.add_argument(
        "--min-confidence",
        type=int,
        default=70,
        help="Minimum confidence level (0-100). Default: 70",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default=".venv,venv,__pycache__,tests,scripts,data,logs,tmp,temp,vendor,ui",
        help="Comma-separated exclude patterns",
    )
    parser.add_argument(
        "--ignore-names",
        type=str,
        default="handler,entry,user_id,entry_id,session_id,event,details,token",
        help="Comma-separated names to ignore",
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
        help="Custom paths to check (default: src/ai_assistant subdirs)",
    )

    args = parser.parse_args()

    # Determine paths: custom or default source tree
    if args.paths:
        paths = args.paths
    else:
        paths = _default_source_paths()
        if not paths:
            print("Error: no source directories found under src/ai_assistant")
            return 1

    # Filter existing
    existing = [p for p in paths if Path(p).exists()]
    for p in paths:
        if not Path(p).exists():
            print(f"Warning: skipping missing directory: {p}")

    if not existing:
        print("Error: no valid directories to check")
        return 1

    # Build command
    cmd = [sys.executable, "-m", "vulture"]
    cmd.extend(existing)

    exclude = [e.strip() for e in args.exclude.split(",") if e.strip()]
    if exclude:
        cmd.extend(["--exclude", ",".join(exclude)])

    cmd.extend(["--min-confidence", str(args.min_confidence)])

    if not args.no_sort_by_size:
        cmd.append("--sort-by-size")

    if not args.no_ignore_defaults:
        ignore = [n.strip() for n in args.ignore_names.split(",") if n.strip()]
        if ignore:
            cmd.extend(["--ignore-names", ",".join(ignore)])

    print(f"Running: {' '.join(cmd)}")
    print("-" * 55)

    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
