#!/usr/bin/env python3
"""Mutation testing wrapper — uses mutmut (industrial standard).

Usage:
    python dev/scripts/check_mutations.py              # full project mutation test
    python dev/scripts/check_mutations.py --quick      # sacred core only (fast)
"""

import argparse
import subprocess
import sys
from pathlib import Path

MUTATION_SCORE_THRESHOLD = 80.0
MUTANT_SURVIVED = 2


def _mutmut_runs_on_platform() -> bool:
    """Check if mutmut actually executes, not just installed."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mutmut", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "WSL" not in result.stdout and "WSL" not in result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    print(f">> {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _parse_score(output: str) -> float | None:
    """Extract mutation score from mutmut JSON output."""
    import json

    try:
        data = json.loads(output)
        if isinstance(data, dict):
            return float(data.get("mutation_score", 0))
        if isinstance(data, list) and data:
            return float(data[0].get("mutation_score", 0))
    except (json.JSONDecodeError, ValueError, AttributeError):
        pass
    return None


def main() -> int:
    if not _mutmut_runs_on_platform():
        print("=" * 55)
        print("MUTATION TESTING — Skipped")
        print("=" * 55)
        print(">> mutmut is not available on this platform")
        print("   See: https://github.com/boxed/mutmut/issues/397")
        print(
            "   Run in WSL: wsl -e bash -c "
            "'cd /mnt/d/ai && python dev/scripts/check_mutations.py'"
        )
        return 0

    parser = argparse.ArgumentParser(description="Mutation testing via mutmut")
    parser.add_argument("--quick", action="store_true", help="Sacred core only")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    print(f"Project root: {project_root}")

    if args.quick:
        paths = ["src/ai_assistant/core/"]
        print("=" * 55)
        print("MUTATION TESTING — Sacred Core only")
        print("=" * 55)
    else:
        paths = None
        print("=" * 55)
        print("MUTATION TESTING — Full project")
        print("=" * 55)

    cmd = [sys.executable, "-m", "mutmut", "run"]
    if paths:
        cmd.extend(["--paths-to-mutate", ",".join(paths)])
    result = _run(cmd, project_root)

    if result.returncode not in (0, MUTANT_SURVIVED):
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print("ERROR: mutmut run failed")
        return 1

    print(result.stdout)

    results_cmd = [sys.executable, "-m", "mutmut", "results", "--json"]
    results = _run(results_cmd, project_root)

    if results.returncode != 0:
        print(results.stderr, file=sys.stderr)
        print("WARNING: Could not retrieve results")
        return 1

    score = _parse_score(results.stdout)
    if score is None:
        print("WARNING: Could not parse mutation score")
        print("Raw output:")
        print(results.stdout[:500])
        return 1

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
