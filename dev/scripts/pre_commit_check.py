#!/usr/bin/env python3
"""Pre-commit checks — lightweight regex scanner."""

import re
import sys
from pathlib import Path

R, Y, G, RST = "\033[31m", "\033[33m", "\033[32m", "\033[0m"


def _find_src_root() -> Path:
    """Find src/ai_assistant relative to script location."""
    script_dir = Path(__file__).resolve().parent
    # Try project root (parent of dev/)
    project_root = script_dir.parent
    src = project_root / "src" / "ai_assistant"
    if src.exists():
        return src
    # Fallback: cwd
    cwd_src = Path.cwd() / "src" / "ai_assistant"
    if cwd_src.exists():
        return cwd_src
    raise FileNotFoundError(f"src/ai_assistant not found in {project_root} or {Path.cwd()}")


def _scan_file(path: Path, pattern: re.Pattern, rule: str, warn_only: bool = False) -> list[tuple[Path, int, str, bool]]:
    """Scan single file for pattern."""
    found = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{Y}{path}:READ_ERROR:{e}{RST}")
        return found

    for n, line in enumerate(text.splitlines(), 1):
        # Skip comment lines to reduce false positives
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if pattern.search(line):
            found.append((path, n, rule, warn_only))
    return found


def main() -> int:
    src = _find_src_root()
    issues: list[tuple[Path, int, str, bool]] = []

    # 1. hasattr in adapters
    for p in (src / "adapters").rglob("*.py"):
        issues.extend(_scan_file(p, re.compile(r"hasattr\("), "no-hasattr-in-adapters"))

    # 2. **kwargs in core/ports (llm.py excluded — sampling params open-ended)
    for p in (src / "core/ports").rglob("*.py"):
        if p.name != "llm.py":
            issues.extend(_scan_file(p, re.compile(r"\*\*kwargs"), "no-kwargs-in-ports"))

    # 3. cross-feature imports
    for feat in (src / "features").iterdir():
        if not feat.is_dir():
            continue
        for p in feat.rglob("*.py"):
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                # Skip comments
                if line.strip().startswith("#"):
                    continue
                m = re.search(r"from\s+ai_assistant\.features\.([a-z_]+)", line)
                if m and m.group(1) != feat.name:
                    issues.append((p, n, "no-cross-feature-imports", False))

    # 4. PipelineData mutation — only in adapters/features, not pipeline steps (by design)
    _mut_pat = re.compile(r"\bdata\.(context\s*=|chunks\s*=|response\s*=|errors\.append\()")
    for sub in ("adapters", "features"):
        for p in (src / sub).rglob("*.py"):
            issues.extend(_scan_file(p, _mut_pat, "no-direct-pipeline-mutation"))

    # 5. yaml.safe_load in security.py — warning (currently no-op, kept for future)
    sec_path = src / "api" / "security.py"
    if sec_path.exists():
        issues.extend(_scan_file(sec_path, re.compile(r"yaml\.safe_load"), "yaml-safe-load-warning", True))

    # Output
    for p, n, rule, w in issues:
        print(f"{Y if w else R}{p}:{n}:{rule}{RST}")

    if any(not w for _, _, _, w in issues):
        print(f"{R}BLOCKED{RST}")
        return 1
    if any(w for _, _, _, w in issues):
        print(f"{Y}WARNING{RST}")
    print(f"{G}OK{RST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
