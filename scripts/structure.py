#!/usr/bin/env python3
"""structure.py — compact project tree with .gitignore support and metrics."""

import argparse
import fnmatch
import os
import sys
from datetime import datetime
from pathlib import Path

# Never shown, never traversed
HARD_EXCLUDE = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".hypothesis", ".tox", "node_modules", "dist", "build", ".eggs",
    "htmlcov", "venv",
})

# Shown as folder name + description, but contents are NOT traversed
HIDDEN_FOLDERS = {
    ".git": "Git repository (contents hidden)",
    ".venv": "Python virtual environment (contents hidden)",
    "data": "indexes, yaml profiles, tokenizers and logs",
    "vendor": "llama.cpp binaries and GGUF models",
}

# Files always shown, even if ignored by .gitignore
IMPORTANT_FILES = frozenset({
    "config.yaml", "config.example.yaml",
    "LICENSE", "README.md", "pyproject.toml",
})


def load_patterns(root: Path, filename: str) -> list[str]:
    """Load ignore patterns from a file."""
    path = root / filename
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    """Check if path matches any ignore pattern (basic gitignore rules)."""
    rel = path.relative_to(root).as_posix()
    name = path.name
    for pat in patterns:
        if pat.startswith("!"):
            continue
        if pat.endswith("/"):
            if not path.is_dir():
                continue
            pat_name = pat[:-1]
            if name == pat_name or rel == pat_name or rel.startswith(pat_name + "/"):
                return True
            continue
        if "*" in pat or "?" in pat:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
                return True
            continue
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
        ".pyc", ".pyo", ".so", ".dll", ".exe", ".dylib",
        ".gguf", ".bin", ".pt", ".safetensors", ".cache", ".log",
    }:
        return True
    return False


def fmt_size(n: int) -> str:
    """Human-readable size."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def count_lines(path: Path) -> int:
    """Count lines in a text file."""
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


def build(root: Path, use_color: bool = False) -> str:
    """Generate compact markdown tree with metrics."""
    patterns = load_patterns(root, ".gitignore") + load_patterns(root, ".structureignore")

    entries: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        current = Path(dirpath)

        # Prune hard-excluded directories
        dirnames[:] = [d for d in dirnames if not hard_excluded(current / d, root)]

        # Handle hidden folders: show them, but don't descend
        if current.name in HIDDEN_FOLDERS and current != root:
            entries.append(current)
            dirnames.clear()
            continue

        # Directories
        for d in dirnames:
            d_path = current / d
            if d_path.is_symlink():
                continue
            # Always show hidden folders, even if .gitignored
            if d in HIDDEN_FOLDERS:
                entries.append(d_path)
                continue
            if not is_ignored(d_path, root, patterns):
                entries.append(d_path)

        # Files
        for f in filenames:
            f_path = current / f
            if f_path.is_symlink() or hard_excluded(f_path, root):
                continue
            if f in IMPORTANT_FILES:
                entries.append(f_path)
                continue
            if not is_ignored(f_path, root, patterns):
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

    # Build tree
    tree: dict = {}
    for e in entries:
        node = tree
        parts = e.relative_to(root).parts
        for i, part in enumerate(parts):
            if i == len(parts) - 1 and e.is_file():
                node[part] = None  # file
            else:
                node = node.setdefault(part, {})

    # Replace empty dicts of hidden folders with description string
    for key, desc in HIDDEN_FOLDERS.items():
        if key in tree and isinstance(tree[key], dict) and not tree[key]:
            tree[key] = desc

    def render(node, prefix=""):
        out = []
        # Sort: dirs (dict values) first, then hidden (str), then files (None)
        items = sorted(
            node.items(),
            key=lambda x: (
                not isinstance(x[1], dict),      # directories first
                isinstance(x[1], str),            # then hidden
                x[0].lower()                      # alphabetical
            )
        )
        for name, val in items:
            if isinstance(val, dict):
                out.append(f"{prefix}{name}/")
                out.append(render(val, prefix + "  "))
            elif isinstance(val, str):  # hidden folder with description
                out.append(f"{prefix}{name}/  # {val}")
            else:
                out.append(f"{prefix}{name}")
        return "\n".join(out)

    tree_text = render(tree)

    # Colors
    g = "\x1b[32m" if use_color else ""
    r = "\x1b[0m" if use_color else ""

    return "\n".join([
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
        tree_text,
        "```",
    ])


def main():
    parser = argparse.ArgumentParser(description="Generate compact project structure")
    parser.add_argument("--root", "-r", type=Path, default=None)
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Output file (default: structure.txt in project root)")
    parser.add_argument("--stdout", "-s", action="store_true",
                        help="Print to stdout instead of file")
    parser.add_argument("--color", "-c", action="store_true",
                        help="Colorize terminal output")
    args = parser.parse_args()

    scripts_dir = Path(__file__).parent.resolve()
    if args.root is None:
        if (scripts_dir.parent / "src" / "ai_assistant").exists() or \
           (scripts_dir.parent / "pyproject.toml").exists():
            args.root = scripts_dir.parent
        else:
            args.root = scripts_dir

    if not args.root.exists():
        print(f"ERROR: root path does not exist: {args.root}", file=sys.stderr)
        return 1

    text = build(args.root, use_color=args.color and not args.stdout)

    if args.stdout:
        print(text)
        return 0

    out = args.output or (args.root / "data" / "structure.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"[OK] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
