#!/usr/bin/env python3
"""structure.py — генерация structure.txt в корне проекта."""

import argparse
from pathlib import Path

EXCLUDE_DIRS = {".git", ".venv", "__pycache__"}
EXCLUDE_FILES = {".gitignore", ".env", ".env.local", "*.pyc", "*.pyo"}


def _is_excluded(p: Path, root: Path) -> bool:
    for part in p.relative_to(root).parts:
        if part in EXCLUDE_DIRS:
            return True
    name = p.name
    if name in EXCLUDE_FILES:
        return True
    if p.is_file() and p.suffix.lower() in {".pyc", ".pyo", ".so", ".dll", ".exe"}:
        return True
    return False


def build(root: Path) -> str:
    tree = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink() or _is_excluded(p, root):
            continue
        node = tree
        for part in p.relative_to(root).parts:
            node = node.setdefault(part, {})

    def _render(node, pref=""):
        for i, k in enumerate(sorted(node)):
            last = i == len(node) - 1
            yield f"{pref}{'└── ' if last else '├── '}{k}"
            yield from _render(node[k], pref + ("    " if last else "│   "))

    return "\n".join(
        ["# Project Structure", f"**Root:** `{root}`\n", "```"]
        + list(_render(tree))
        + ["```"]
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root", "-r", type=Path, default=Path(__file__).parent.parent.resolve()
    )
    ap.add_argument("--output", "-o", type=Path, default=None)
    args = ap.parse_args()
    out = args.output or args.root / "structure.txt"
    out.write_text(build(args.root), encoding="utf-8")
    print(f"✅ {out}")


if __name__ == "__main__":
    main()
