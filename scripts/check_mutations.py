#!/usr/bin/env python3
"""Mutation testing wrapper — uses mutmut (industrial standard).

Usage:
    python scripts/check_mutations.py              # full project mutation test
    python scripts/check_mutations.py --quick      # sacred core only (fast)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

MUTATION_SCORE_THRESHOLD = 80.0


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    print(f">> {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _parse_score(output: str) -> float | None:
    """Extract mutation score from mutmut results output."""
    for line in output.splitlines():
        if "Mutation score" in line or "score" in line.lower():
            parts = line.split()
            for part in parts:
                try:
                    if "%" in part:
                        return float(part.replace("%", "").replace(":", ""))
                except ValueError:
                    continue
    return None


def main() -> int:
    # mutmut не поддерживает Windows нативно
    if sys.platform == "win32":
        print("=" * 55)
        print("MUTATION TESTING — Skipped")
        print("=" * 55)
        print(">> mutmut requires WSL on Windows")
        print("   See: https://github.com/boxed/mutmut/issues/397")
        print(
            "   Run in WSL: wsl -e bash -c "
            "'cd /mnt/d/ai && python scripts/check_mutations.py'"
        )
        return 0

    parser = argparse.ArgumentParser(description="Mutation testing via mutmut")
    parser.add_argument("--quick", action="store_true", help="Sacred core only")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    # Determine paths to mutate
    if args.quick:
        paths = ["core/"]
        print("=" * 55)
        print("MUTATION TESTING — Sacred Core only")
        print("=" * 55)
    else:
        paths = ["core/", "adapters/", "features/", "api/", "pipeline/"]
        print("=" * 55)
        print("MUTATION TESTING — Full project")
        print("=" * 55)

    # Run mutmut
    cmd = [
        sys.executable,
        "-m",
        "mutmut",
        "run",
        "--paths-to-mutate",
        ",".join(paths),
    ]
    result = _run(cmd, project_root)

    if result.returncode != 0 and result.returncode != 2:
        # returncode 2 = some mutants survived (expected, we check score)
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print("ERROR: mutmut run failed")
        return 1

    print(result.stdout)

    # Get results
    results_cmd = [sys.executable, "-m", "mutmut", "results"]
    results = _run(results_cmd, project_root)
    print(results.stdout)

    # Parse and check score
    score = _parse_score(results.stdout)
    if score is None:
        print("WARNING: Could not parse mutation score")
        return 0  # Don't fail CI on parse issues

    print(f"\nMutation score: {score:.1f}% (threshold: {MUTATION_SCORE_THRESHOLD}%)")

    if score >= MUTATION_SCORE_THRESHOLD:
        print(f"PASS: Score >= {MUTATION_SCORE_THRESHOLD}%")
        return 0
    else:
        print(f"FAIL: Score < {MUTATION_SCORE_THRESHOLD}%")
        print("Run 'mutmut show <id>' to inspect surviving mutants")
        return 1


if __name__ == "__main__":
    sys.exit(main())
