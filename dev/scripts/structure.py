#!/usr/bin/env python3
"""structure.py — project tree with .gitignore support, metrics,
and human-readable sizes."""

import argparse
import fnmatch
import os
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
    ".venv",
    "venv",
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
    """Check if path matches any ignore pattern.

    Supports basic gitignore semantics:
    - "*.pyc" matches any file with .pyc extension (any depth)
    - "build/" matches directory named "build" (any depth)
    - "exact" matches file or directory named "exact" (any depth)
    """
    rel = path.relative_to(root).as_posix()
    name = path.name
    for pat in patterns:
        # Negative patterns not supported
        if pat.startswith("!"):
            continue
        # Directory pattern
        if pat.endswith("/"):
            if not path.is_dir():
                continue
            pat_name = pat[:-1]
            if fnmatch.fnmatch(name, pat_name):
                return True
            if rel == pat_name or rel.startswith(pat_name + "/"):
                return True
            continue
        # Wildcard pattern — match basename or full relative path
        if "*" in pat or "?" in pat:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
                return True
            continue
        # Exact name match at any depth
        if name == pat or rel == pat or rel.startswith(pat + "/"):
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

    # Collect valid entries with os.walk pruning for hard exclusions
    entries: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)
        # Prune hard-excluded directories
        dirnames[:] = [
            d for d in dirnames
            if not hard_excluded(current / d, root)
        ]
        for d in dirnames:
            d_path = current / d
            if not d_path.is_symlink() and not is_ignored(d_path, root, patterns):
                entries.append(d_path)
        for f in filenames:
            f_path = current / f
            if f_path.is_symlink():
                continue
            if hard_excluded(f_path, root) or is_ignored(f_path, root, patterns):
                continue
            entries.append(f_path)

    # Metrics
    files = [e for e in entries if e.is_file()]
    py_files = [e for e in files if e.suffix == ".py"]
    total_size = 0
    for f in files:
        try:
            total_size += f.stat().st_size
        except OSError:
            pass
    py_loc = sum(count_lines(f) for f in py_files)

    # Tree rendering: directories first, then files, both alphabetically
    tree: dict[str, Any] = {}
    for e in entries:
        node: dict[str, Any] = tree
        parts = e.relative_to(root).parts
        for i, part in enumerate(parts):
            if i == len(parts) - 1 and e.is_file():
                node[part] = None  # File marker
            else:
                node = node.setdefault(part, {})  # Directory

    def render(node: dict[str, Any], prefix: str = "") -> list[str]:
        dirs = sorted(k for k, v in node.items() if v is not None)
        files_only = sorted(k for k, v in node.items() if v is None)
        items = dirs + files_only
        out: list[str] = []
        for i, k in enumerate(items):
            is_last = i == len(items) - 1
            branch = "└── " if is_last else "├── "
            out.append(f"{prefix}{branch}{k}")
            if node[k] is not None:  # recurse into directory
                ext = "    " if is_last else "│   "
                out.extend(render(node[k], prefix + ext))
        return out

    # ANSI colors
    g = "[32m" if use_color else ""
    r = "[0m" if use_color else ""

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

    if not args.root.exists():
        print(f"ERROR: root path does not exist: {args.root}")
        return 1

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
