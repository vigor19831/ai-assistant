#!/usr/bin/env python3
"""
context_build.py — AI Context Builder.

Folder processing rules:
  .venv .git data sources vendor ui — always fully excluded
  docs — folder excluded; ai_rules / architecture / drift embedded in full
  scripts tests — file list in rules/compact, full content in full mode
"""

import argparse
import ast
import contextlib
import fnmatch
import os
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from ai_assistant.core.logger import get_logger

logger = get_logger("context_build")


# ============================================================================
# SETTINGS
# ============================================================================

# ALWAYS excluded — do not scan, do not show
HARD_EXCLUDED = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", ".env", "node_modules", ".idea", ".vscode",
    "dist", "build",
    "data", "sources", "vendor",
    ".test_tmp", ".hypothesis",
    "ui",
}

# Docs files that are ALWAYS embedded in context (search in root and docs/)
REQUIRED_DOCS = ["ai_rules.md", "architecture.md", "drift.md"]


# Files that are ALWAYS full in compact mode (except tests/scripts)
ALWAYS_FULL = {
    "config.example.yaml", "pyproject.toml", ".gitignore",
}

# REQUIRED_DOCS are the ground truth (ai_rules §0) — they reach the AI in
# FULL, always. This is a loud tripwire, not a truncation limit: crossing
# it means the doc has outgrown the context budget — compact or split it.
_DOC_SIZE_WARNING: int = 80000

# Skip
SKIP_FILES = [
    "*.pyc", "*.pyo", "*.so", "*.dll", "*.exe",
    "*.gguf", "*.bin", "*.pt", "*.pth", "*.onnx", "*.safetensors",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp",
    "*.mp3", "*.wav", "*.lock", ".DS_Store", "Thumbs.db",
    "*.log", "*.pid",
    "structure.txt",
    "*context_build_*.md",
    "*.test.yaml", "*.test.yml",
    # Runtime scripts — not part of project code
    "run.py", "launcher.py",
    ".gitattributes", ".coverage",
]


# ============================================================================
# HELPERS
# ============================================================================

def find_project_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    if script_dir.name == "scripts" and script_dir.parent.exists():
        return script_dir.parent
    for parent in [script_dir, *script_dir.parents]:
        if (parent / "README.md").exists() and (parent / "pyproject.toml").exists():
            return parent
    return script_dir.parent


def should_skip(rel_path: str) -> bool:
    basename = os.path.basename(rel_path)
    for pat in SKIP_FILES:
        if fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(rel_path, pat):
            return True
    return False


def count_loc(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def extract_imports(source: str) -> tuple[list[str], list[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    internal, external = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("ai_assistant"):
                names = ", ".join(a.name for a in node.names)
                internal.append(f"{mod}: {names}")
            elif mod and not mod.startswith("."):
                external.append(mod.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                (internal if name == "ai_assistant" else external).append(name)
    return sorted(set(internal)), sorted(set(external))


# ============================================================================
# SCAN
# ============================================================================

def scan(
    root: Path, mode: str
) -> tuple[
    list[tuple[str, str | None, int, str]],
    list[tuple[str, str | None]],
    dict[str, int],
]:
    """Scan files according to mode."""
    all_files: list[tuple[str, str | None, int, str]] = []
    py_files: list[tuple[str, str | None]] = []
    metrics = {"total": 0, "py": 0, "loc": 0, "classes": 0, "funcs": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        # Hard exclude
        dirnames[:] = [d for d in dirnames if d not in HARD_EXCLUDED]

        rel_dir = Path(dirpath).relative_to(root)
        parts = rel_dir.parts

        # Determine folder type
        is_docs = "docs" in parts
        is_scripts = "scripts" in parts
        is_tests = "tests" in parts

        for fname in sorted(filenames):
            path = Path(dirpath) / fname
            rel = path.relative_to(root).as_posix()

            if should_skip(rel):
                continue

            size = path.stat().st_size

            is_py = rel.endswith(".py")
            basename = os.path.basename(rel)

            # docs — do not read content (except REQUIRED_DOCS, added later)
            if is_docs:
                continue  # skip, REQUIRED_DOCS will be added later

            # Read content only if needed for this mode
            need_content = mode != "rules" or is_py
            content = None
            if need_content:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    logger.warning("Skipping unreadable file: %s (%s)", rel, exc)
                    continue

            if is_py:
                metrics["py"] += 1
                # content is None only for non-py files in "rules"
                # mode; a py file is always read above.
                metrics["loc"] += count_loc(content or "")
                py_files.append((rel, content))
                try:
                    tree = ast.parse(content or "")
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            metrics["classes"] += 1
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            metrics["funcs"] += 1
                except SyntaxError:
                    pass

            # Determine display type
            if mode == "rules":
                all_files.append((rel, None, size, "listed"))
                metrics["total"] += 1

            elif mode == "full":
                # In full: scripts and tests fully, others too
                all_files.append((rel, content, size, "full"))
                metrics["total"] += 1

            else:  # compact
                if is_scripts or is_tests:
                    if basename == "conftest.py":
                        all_files.append((rel, content, size, "full"))
                    else:
                        # List only
                        all_files.append((rel, None, size, "listed"))
                elif (
                    basename in ALWAYS_FULL
                    or "core" in parts
                    or "api" in parts
                    or "features" in parts
                    or "handlers" in basename
                    or "schemas" in basename
                ):
                    all_files.append((rel, content, size, "full"))
                elif is_py:
                    all_files.append((rel, content, size, "signature"))
                else:
                    all_files.append((rel, content, size, "listed"))
                metrics["total"] += 1

    # Add REQUIRED_DOCS separately (search in root and docs/)
    for doc_name in REQUIRED_DOCS:
        found = False
        for location in [root / doc_name, root / "docs" / doc_name]:
            if location.exists():
                try:
                    content = location.read_text(encoding="utf-8", errors="replace")
                    all_files.append((doc_name, content, len(content), "doc"))
                    found = True
                    break
                except OSError:
                    continue
        if not found:
            logger.warning("Required doc not found: %s", doc_name)

    return all_files, py_files, metrics


# ============================================================================
# SIGNATURES
# ============================================================================

def extract_signature(source: str, rel_path: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"# Syntax error: {e}\n"

    lines = [f"# API: {rel_path}", ""]

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            with contextlib.suppress(Exception):
                lines.append(ast.unparse(node))

        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
            sig = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
            doc = ast.get_docstring(node)
            if doc:
                sig += f'''\n    """{doc[:200]}"""'''
            lines.append(sig)
            lines.append("")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                args = ast.unparse(node.args)
            except Exception:
                args = "..."
            async_p = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            doc = ast.get_docstring(node)
            sig = f"{async_p}def {node.name}({args}):"
            if doc:
                sig += f'''\n    """{doc[:200]}"""'''
            lines.append(sig)
            lines.append("")

    return "\n".join(lines)


# ============================================================================
# BUILD MARKDOWN
# ============================================================================

def build_markdown(
    root: Path,
    mode: str,
    all_files: list[tuple[str, str | None, int, str]],
    py_files: list[tuple[str, str | None]],
    metrics: dict[str, int],
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Split by type; doc/full contents are always read (None is a
    # "rules"-mode marker for listed files only).
    doc_files: list[tuple[str, str]] = [
        (r, c) for r, c, s, t in all_files if t == "doc" and c is not None
    ]
    full_files: list[tuple[str, str]] = [
        (r, c) for r, c, s, t in all_files if t == "full" and c is not None
    ]
    sig_files: list[tuple[str, str]] = [
        (r, c) for r, c, s, t in all_files if t == "signature" and c is not None
    ]
    listed_files: list[str] = [r for r, c, s, t in all_files if t == "listed"]

    lines = [
        "# AI Context",
        f"> **Generated:** {now} | **Mode:** `{mode}`",
        f"> **Metrics:** {metrics['total']} files | {metrics['py']} Python"
        f" | {metrics['loc']:,} LOC",
        f"> **Full:** {len(full_files)} | **Signatures:** {len(sig_files)}"
        f" | **Listed:** {len(listed_files)}",
        "",
        "---",
        "",
    ]

    # AI Rules (from doc_files)
    _doc_titles = {
        "ai_rules.md": "AI Development Guidelines",
        "architecture.md": "Architectural Strategy",
        "drift.md": "Known Drift",
    }
    for rel, content in doc_files:
        title = _doc_titles.get(rel, "Project Documentation")
        lines.extend([
            f"## {title}",
            f"> Auto-extracted from: `{rel}`",
        ])
        if len(content) > _DOC_SIZE_WARNING:
            # Ground truth is never cut (ai_rules §0): embed in full,
            # warn loudly — in the artifact AND in the generation log.
            warning = (
                f"> **WARNING:** `{rel}` is {len(content):,} chars "
                f"(tripwire {_DOC_SIZE_WARNING:,}) — embedded IN FULL, but "
                "the doc has outgrown the context budget: compact or split it."
            )
            logger.warning(
                "Doc over size tripwire, embedded in full: %s (%d chars)",
                rel, len(content),
            )
            lines.append(warning)
        lines.extend([
            "```markdown",
            content,
            "```",
            "",
            "---",
            "",
        ])

    # Structure
    lines.extend([
        "## Structure",
        "```",
    ])
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in HARD_EXCLUDED]
        rel_dir = Path(dirpath).relative_to(root)
        depth = len(rel_dir.parts) - 1 if rel_dir != Path(".") else 0
        if rel_dir != Path("."):
            lines.append(f"{'    ' * depth}{rel_dir.name}/")
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel_file = fpath.relative_to(root).as_posix()
            if not should_skip(rel_file):
                lines.append(f"{'    ' * (depth + 1)}{fname}")
    lines.extend(["```", "", "---", ""])

    # Dependencies
    if mode in ("rules", "compact") and py_files:
        lines.extend(["## Dependencies", ""])
        graph: dict[str, list[str]] = defaultdict(list)
        for rel, file_content in py_files:
            if file_content is None:
                continue
            internal, _ = extract_imports(file_content)
            if internal:
                graph[rel] = internal
        for py_rel, imports in sorted(graph.items()):
            lines.append(f"- `{py_rel}`")
            for imp in imports:
                lines.append(f"  - → `{imp}`")
            lines.extend(["", "---", ""])

    # File Inventory
    lines.extend(["## Files", ""])
    if full_files:
        lines.append("### Full Content")
        for r, _ in sorted(full_files):
            lines.append(f"- `{r}`")
        lines.append("")
    if sig_files:
        lines.append("### Signatures Only")
        for r, _ in sorted(sig_files):
            lines.append(f"- `{r}`")
        lines.append("")
    if listed_files:
        lines.append("### Listed Only (no content)")
        for r in sorted(listed_files):
            lines.append(f"- `{r}`")
        lines.append("")
    lines.extend(["---", ""])

    # Full Content
    if full_files:
        lines.extend(["## Full Code", ""])
        for rel, content in sorted(full_files, key=lambda x: x[0]):
            if rel.endswith(".py"):
                ext = "python"
            elif rel.endswith((".yaml", ".yml")):
                ext = "yaml"
            elif rel.endswith(".toml"):
                ext = "toml"
            elif rel.endswith(".json"):
                ext = "json"
            elif rel.endswith(".md"):
                ext = "markdown"
            elif rel.endswith(".j2"):
                ext = "jinja"
            else:
                ext = "text"
            lines.extend([f"### `{rel}`", f"```{ext}", content, "```", ""])

    # Signatures
    if sig_files:
        lines.extend(["## API Signatures", ""])
        for rel, content in sorted(sig_files, key=lambda x: x[0]):
            sig = extract_signature(content, rel)
            lines.extend([f"### `{rel}`", "```python", sig, "```", ""])

    return "\n".join(lines)


# ============================================================================
# WRITE
# ============================================================================

def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()


# ============================================================================
# MENU
# ============================================================================

def menu() -> str:
    print("\n  AI Context Builder")
    print("  ==================")

    options = [
        "rules  — structure, rules, dependencies (zero code)",
        "compact — critical files + signatures for the rest",
        "full — EVERYTHING fully (including tests and scripts)",
    ]

    print("\nSelect mode:")
    for i, opt in enumerate(options, 1):
        marker = ">" if i == 2 else " "
        print(f"  {marker} [{i}] {opt}")

    while True:
        try:
            raw = input("\nChoice [1-3], Enter = 2: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if raw == "":
            return "compact"
        if raw.isdigit() and 1 <= int(raw) <= 3:
            return ["rules", "compact", "full"][int(raw) - 1]
        print("Invalid input")


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["rules", "compact", "full"], default="compact"
    )
    parser.add_argument("--output", default=None)

    if len(sys.argv) <= 1:
        mode = menu()
        args = parser.parse_args([])  # Get defaults for output
    else:
        args = parser.parse_args()
        mode = args.mode

    root = find_project_root()

    all_files, py_files, metrics = scan(root, mode)

    # Recalculate metrics based on what actually goes into context
    metrics["total"] = len(all_files)
    metrics["py"] = sum(1 for r, c, s, t in all_files if r.endswith(".py"))
    metrics["loc"] = sum(count_loc(c) for r, c, s, t in all_files if c is not None)

    logger.info(
        "Total: %d | Python: %d | LOC: %d",
        metrics["total"], metrics["py"], metrics["loc"],
    )

    md = build_markdown(root, mode, all_files, py_files, metrics)

    out_name = args.output or f"context_build_{mode}.md"
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / out_name
    write_file(out_path, md)

    print(f"\nDone: {out_path} ({len(md):,} chars, ~{len(md)//4:,} tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
