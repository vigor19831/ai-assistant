#!/usr/bin/env python3
"""Pre-commit checks — lightweight regex scanner."""

import re
import sys
from pathlib import Path

R, Y, G, RST = "\033[31m", "\033[33m", "\033[32m", "\033[0m"


def _find_src_root() -> Path:
    """Find src/ai_assistant relative to script location."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    src = project_root / "src" / "ai_assistant"
    if src.exists():
        return src
    cwd_src = Path.cwd() / "src" / "ai_assistant"
    if cwd_src.exists():
        return cwd_src
    raise FileNotFoundError(f"src/ai_assistant not found in {project_root} or {Path.cwd()}")


def _clean_line(line: str) -> str:
    """Remove string literals and inline comments to reduce false positives."""
    line = re.sub(r"'[^']*'", "''", line)
    line = re.sub(r'"[^"]*"', '""', line)
    if "#" in line:
        line = line.split("#")[0]
    return line


def _scan_file(
    path: Path,
    pattern: re.Pattern,
    rule: str,
    warn_only: bool = False,
) -> list[tuple[Path, int, str, bool]]:
    """Scan single file for pattern."""
    found: list[tuple[Path, int, str, bool]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError) as e:
        print(f"{Y}{path}:READ_ERROR:{e}{RST}")
        return found

    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if pattern.search(_clean_line(line)):
            found.append((path, n, rule, warn_only))
    return found


def main() -> int:
    src = _find_src_root()
    issues: list[tuple[Path, int, str, bool]] = []

    # 1. hasattr / isinstance in adapters
    for p in (src / "adapters").rglob("*.py"):
        issues.extend(_scan_file(p, re.compile(r"hasattr\("), "no-hasattr-in-adapters", warn_only=True))
        issues.extend(_scan_file(p, re.compile(r"isinstance\("), "no-isinstance-in-adapters", warn_only=True))

    # 2. **kwargs in core/ports (llm.py excluded — sampling params open-ended)
    for p in (src / "core/ports").rglob("*.py"):
        if p.name != "llm.py":
            issues.extend(_scan_file(p, re.compile(r"\*\*kwargs"), "no-kwargs-in-ports"))

    # 3. cross-feature imports (absolute + relative)
    for feat in (src / "features").iterdir():
        if not feat.is_dir():
            continue
        for p in feat.rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                clean = _clean_line(line)
                m = re.search(r"(?:from|import)\s+ai_assistant\.features\.([a-z_]+)", clean)
                if m and m.group(1) != feat.name:
                    issues.append((p, n, "no-cross-feature-imports", False))
                m_rel = re.search(r"from\s+\.\.([a-z_]+)", clean)
                if m_rel and m_rel.group(1) != feat.name:
                    issues.append((p, n, "no-cross-feature-imports", False))

    # 4. PipelineData mutation in adapters/features
    _mut_pat = re.compile(
        r"\bdata\.("
        r"context\s*=|"
        r"chunks\s*=|"
        r"response\s*=|"
        r"metadata\s*\[.*\]\s*=|"
        r"metadata\.update\s*\(|"
        r"errors\.(append|extend)\s*\(|"
        r"errors\s*\+=)"
    )
    for sub in ("adapters", "features"):
        for p in (src / sub).rglob("*.py"):
            issues.extend(_scan_file(p, _mut_pat, "no-direct-pipeline-mutation"))

    # 5. print / pprint / logging.basicConfig in production code
    _prod_pat = re.compile(r"\b(print|pprint)\s*\(|logging\.basicConfig\s*\(")
    for p in src.rglob("*.py"):
        # Allow in dev/ and ops/ scripts, but not in core/adapters/features/api/pipeline
        # Exclude files in dev/ or ops/ directories at any level
        if any(part in ("dev", "ops") for part in p.parts):
            continue
        issues.extend(_scan_file(p, _prod_pat, "no-print-in-production"))

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
