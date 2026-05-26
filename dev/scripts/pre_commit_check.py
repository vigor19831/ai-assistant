#!/usr/bin/env python3
"""Pre-commit checks — lightweight regex scanner."""

from __future__ import annotations

import re
import sys
from pathlib import Path

R, Y, G, RST = "\033[31m", "\033[33m", "\033[32m", "\033[0m"
issues: list[tuple[Path, int, str, bool]] = []


def add(path: Path, pat: re.Pattern, rule: str, warn_only: bool = False) -> None:
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if pat.search(line):
            issues.append((path, n, rule, warn_only))


src = Path("src/ai_assistant")

# 1. hasattr in adapters
for p in (src / "adapters").rglob("*.py"):
    add(p, re.compile(r"hasattr\("), "no-hasattr-in-adapters")

# 2. **kwargs in core/ports (llm.py исключён — sampling params open-ended)
for p in (src / "core/ports").rglob("*.py"):
    if p.name != "llm.py":
        add(p, re.compile(r"\*\*kwargs"), "no-kwargs-in-ports")

# 3. cross-feature imports
for feat in (src / "features").iterdir():
    if feat.is_dir():
        for p in feat.rglob("*.py"):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                m = re.search(r"from\s+ai_assistant\.features\.([a-z_]+)", line)
                if m and m.group(1) != feat.name:
                    issues.append((p, n, "no-cross-feature-imports", False))

# 4. PipelineData mutation — только в adapters/features, не в pipeline steps (by design)
_mut_pat = re.compile(r"\bdata\.(context\s*=|chunks\s*=|errors\.append\()")
for sub in ("adapters", "features"):
    for p in (src / sub).rglob("*.py"):
        add(p, _mut_pat, "no-direct-pipeline-mutation")

# 5. yaml.safe_load in security.py — warning
add(
    src / "api/security.py",
    re.compile(r"yaml\.safe_load"),
    "yaml-safe-load-warning",
    True,
)

for p, n, rule, w in issues:
    print(f"{Y if w else R}{p}:{n}:{rule}{RST}")

if any(not w for _, _, _, w in issues):
    print(f"{R}BLOCKED{RST}")
    sys.exit(1)
if any(w for _, _, _, w in issues):
    print(f"{Y}WARNING{RST}")
print(f"{G}OK{RST}")
