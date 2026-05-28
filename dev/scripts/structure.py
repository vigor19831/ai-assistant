#!/usr/bin/env python3
"""structure.py — project tree with .gitignore support, metrics,
and human-readable sizes."""

import argparse
import fnmatch
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Hard exclusions — never traversed
HARD_EXCLUDE = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".tox",
    "node_modules",
    "dist",
    "build",
    ".eggs",
    "htmlcov",
}


def load_patterns(root: Path, filename: str) -> list[str]:
    """Load ignore patterns from a file (e.g. .gitignore, .structureignore)."""
    path = root / filename
    if not path.exists():
        return []
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    """Check if path matches any ignore pattern."""
    rel = path.relative_to(root).as_posix()
    name = path.name
    for pat in patterns:
        # Directory pattern
        if pat.endswith("/") and path.is_dir():
            if fnmatch.fnmatch(rel + "/", pat) or fnmatch.fnmatch(name + "/", pat):
                return True
        # File or wildcard pattern
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat):
            return True
    return False


def hard_excluded(path: Path, root: Path) -> bool:
    """Check against hard-coded exclusions."""
    for part in path.relative_to(root).parts:
        if part in HARD_EXCLUDE:
            return True
        if part.endswith(".egg-info"):
            return True
    if path.is_file() and path.suffix.lower() in {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".exe",
        ".dylib",
    }:
        return True
    return False


def fmt_size(n: int) -> str:
    """Human-readable size."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}" if size != int(size) else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def count_lines(path: Path) -> int:
    """Count lines in a text file."""
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


def build(root: Path, use_color: bool = False) -> str:
    """Generate markdown tree with metrics."""
    patterns = load_patterns(root, ".gitignore") + load_patterns(
        root, ".structureignore"
    )

    # Collect valid entries
    entries: list[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            continue
        # Show .venv as a single marker, never traverse inside
        rel_parts = p.relative_to(root).parts
        if ".venv" in rel_parts:
            if not (len(rel_parts) == 1 and p.name == ".venv"):
                continue
        if hard_excluded(p, root) or is_ignored(p, root, patterns):
            continue
        entries.append(p)

    # Metrics
    files = [e for e in entries if e.is_file()]
    py_files = [e for e in files if e.suffix == ".py"]
    total_size = sum(f.stat().st_size for f in files)
    py_loc = sum(count_lines(f) for f in py_files)

    # Tree rendering: directories first, then files, both alphabetically
    tree: dict[str, Any] = {}
    for e in entries:
        node: dict[str, Any] = tree
        for part in e.relative_to(root).parts:
            node = node.setdefault(part, {})

    def render(node: dict[str, Any], prefix: str = "") -> list[str]:
        # Separate dirs and files: dirs have non-empty dict values
        dirs = sorted(k for k, v in node.items() if v)
        files_only = sorted(k for k, v in node.items() if not v)
        items = dirs + files_only
        out: list[str] = []
        for i, k in enumerate(items):
            is_last = i == len(items) - 1
            branch = "└── " if is_last else "├── "
            out.append(f"{prefix}{branch}{k}")
            if node[k]:  # recurse into directory
                ext = "    " if is_last else "│   "
                out.extend(render(node[k], prefix + ext))
        return out

    # ANSI colors
    g = "\033[32m" if use_color else ""
    r = "\033[0m" if use_color else ""

    lines = [
        f"{g}# Project Structure{r}",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Root:** `{root}`",
        "",
        "## Summary",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total files | {len(files)} |",
        f"| Python files | {len(py_files)} |",
        f"| Python LOC | {py_loc:,} |",
        f"| Total size | {fmt_size(total_size)} |",
        "",
        "```",
    ]
    lines.extend(render(tree))
    lines.append("```")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate project structure file")
    ap.add_argument("--root", "-r", type=Path, default=None)
    ap.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file (default: structure.txt)",
    )
    ap.add_argument(
        "--stdout", "-s", action="store_true", help="Print to stdout instead of file"
    )
    ap.add_argument(
        "--color", "-c", action="store_true", help="Colorize terminal output"
    )
    args = ap.parse_args()

    _dev = Path(__file__).parent.parent.resolve()
    if args.root is None:
        # Scan real project root, write output to dev/
        if (_dev.parent / "src" / "ai_assistant").exists() or (
            _dev.parent / "pyproject.toml"
        ).exists():
            args.root = _dev.parent
        else:
            args.root = _dev

    text = build(args.root, use_color=args.color and not args.stdout)

    if args.stdout:
        print(text)
    else:
        out = args.output or _dev / "structure.txt"
        out.write_text(text, encoding="utf-8")
        print(f"✅ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
