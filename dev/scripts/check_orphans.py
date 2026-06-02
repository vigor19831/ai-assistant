#!/usr/bin/env python3
"""check_orphans.py — Find dead code, orphaned files, and stale references.

Usage:
    python dev/scripts/check_orphans.py

Exit codes:
    0 — no issues
    1 — orphaned files or stale references found
    2 — internal error
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


# ── Configuration ────────────────────────────────────────────────────────────
SRC_DIR = Path("src/ai_assistant")
ADAPTER_INIT = SRC_DIR / "adapters" / "__init__.py"
CORE_PORTS_DIR = SRC_DIR / "core" / "ports"
PYPYPROJECT_TOML = Path("pyproject.toml")

# Files/directories to skip entirely
SKIP_PATHS: set[str] = {
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
    "ui",
    "data",
    "logs",
    "tmp",
    "temp",
    "dev",
    "ops",
}

SKIP_FILES: set[str] = {"__init__.py", "main.py"}


# ── Helpers ──────────────────────────────────────────────────────────────────
def _should_skip(path: Path) -> bool:
    return any(part in SKIP_PATHS for part in path.parts)


def _collect_all_py_files(root: Path) -> list[Path]:
    return [
        f for f in root.rglob("*.py")
        if not _should_skip(f)
    ]


def _path_to_module(path: Path, root: Path, for_import_resolution: bool = False) -> str:
    """Convert file path to dotted module name.

    src/ai_assistant/pipeline/__init__.py → ai_assistant.pipeline
    src/ai_assistant/pipeline/steps.py → ai_assistant.pipeline.steps

    If for_import_resolution=True, __init__.py keeps the .__init__ suffix
    so that relative imports resolve correctly.
    """
    rel = path.relative_to(root.parent)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        if for_import_resolution:
            parts[-1] = "__init__"
        else:
            parts = parts[:-1]
    else:
        parts[-1] = Path(parts[-1]).stem
    return ".".join(parts)


def _extract_imports(text: str, current_module: str = "") -> set[str]:
    """Parse Python source and collect all imported module paths.

    Also resolves relative imports to absolute ones using current_module.
    """
    imports: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level  # relative import level (0 = absolute)

            # Resolve relative imports
            if level > 0 and current_module:
                parts = current_module.split(".")
                # Go up 'level' times
                if len(parts) >= level:
                    base = ".".join(parts[:-level])
                else:
                    base = ""
                if module:
                    resolved = f"{base}.{module}" if base else module
                else:
                    resolved = base
            else:
                resolved = module

            if resolved:
                imports.add(resolved)
            for alias in node.names:
                if resolved:
                    imports.add(f"{resolved}.{alias.name}")
                imports.add(alias.name)
    return imports


# ── Checks ───────────────────────────────────────────────────────────────────
def check_orphaned_files(all_files: list[Path]) -> list[str]:
    """Find .py files that are never imported by anyone."""
    imports: set[str] = set()
    for f in all_files:
        try:
            # For import resolution, __init__.py needs .__init__ suffix
            dotted = _path_to_module(f, SRC_DIR, for_import_resolution=True)
            imports.update(_extract_imports(f.read_text(encoding="utf-8"), dotted))
        except Exception:
            continue

    orphaned: list[str] = []
    for f in sorted(all_files):
        if f.name in SKIP_FILES:
            continue
        # For orphaned detection, use package name (no .__init__)
        dotted = _path_to_module(f, SRC_DIR, for_import_resolution=False)
        pkg_parts = dotted.split(".")
        parent_pkg = ".".join(pkg_parts[:-1]) if len(pkg_parts) >= 2 else ""

        # Check if anyone imports this module
        found = False
        for imp in imports:
            # Direct import: ai_assistant.pipeline.steps
            if imp == dotted:
                found = True
                break
            # Submodule import: from ai_assistant.pipeline import steps
            if parent_pkg and imp == parent_pkg:
                found = True
                break
            # Name import: import steps (unlikely but possible)
            if imp == f.stem:
                found = True
                break
        if not found:
            orphaned.append(str(f))
    return orphaned


def check_orphaned_ports(all_files: list[Path]) -> list[str]:
    """Find port files in core/ports/ that are never imported."""
    if not CORE_PORTS_DIR.exists():
        return []

    imports: set[str] = set()
    for f in all_files:
        try:
            dotted = _path_to_module(f, SRC_DIR, for_import_resolution=True)
            imports.update(_extract_imports(f.read_text(encoding="utf-8"), dotted))
        except Exception:
            continue

    orphaned: list[str] = []
    for f in sorted(CORE_PORTS_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        dotted = f"ai_assistant.core.ports.{f.stem}"
        found = any(
            imp == dotted or imp.endswith(f".{f.stem}")
            for imp in imports
        )
        if not found:
            orphaned.append(str(f))
    return orphaned


def check_adapter_init_consistency() -> list[str]:
    """Check that __all__ entries in adapters/__init__.py actually exist in imports."""
    if not ADAPTER_INIT.exists():
        return []

    issues: list[str] = []
    text = ADAPTER_INIT.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"Syntax error in {ADAPTER_INIT}: {exc}"]

    all_names: list[str] = []
    imported_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_names.append(elt.value)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)

    for name in all_names:
        if name not in imported_names:
            issues.append(f"{ADAPTER_INIT}: __all__ contains '{name}' but it is not imported")
    return issues


def check_pyproject_mypy_overrides() -> list[str]:
    """Check that mypy override modules actually exist."""
    if not PYPYPROJECT_TOML.exists():
        return []

    import tomllib

    issues: list[str] = []
    try:
        with PYPYPROJECT_TOML.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        return [f"Cannot read {PYPYPROJECT_TOML}: {exc}"]

    overrides = data.get("tool", {}).get("mypy", {}).get("overrides", [])
    for override in overrides:
        for mod in override.get("module", []):
            # Handle wildcards
            if "*" in mod:
                continue

            parts = mod.split(".")
            # Skip "ai_assistant" prefix since SRC_DIR is already src/ai_assistant
            # ai_assistant.api.security → parts = ["ai_assistant", "api", "security"]
            # We need: src/ai_assistant/api/security.py
            rel_parts = parts[1:] if parts[0] == "ai_assistant" else parts

            if not rel_parts:
                continue

            # file:  api.security → src/ai_assistant/api/security.py
            file_path = SRC_DIR
            for part in rel_parts[:-1]:
                file_path = file_path / part
            file_path = file_path / (rel_parts[-1] + ".py")

            # package: api → src/ai_assistant/api/__init__.py
            pkg_path = SRC_DIR
            for part in rel_parts:
                pkg_path = pkg_path / part
            pkg_path = pkg_path / "__init__.py"

            # directory (for namespace packages)
            dir_path = SRC_DIR
            for part in rel_parts:
                dir_path = dir_path / part

            exists = (
                file_path.exists()
                or pkg_path.exists()
                or (dir_path.exists() and dir_path.is_dir())
            )
            if not exists:
                issues.append(
                    f"{PYPYPROJECT_TOML}: mypy override module '{mod}' does not exist"
                )
    return issues


def check_compile_all(all_files: list[Path]) -> list[str]:
    """Verify every .py file compiles without syntax errors."""
    import py_compile

    issues: list[str] = []
    for f in sorted(all_files):
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as exc:
            issues.append(f"{f}: compile error — {exc}")
    return issues


# ── Main ─────────────────────────────────────────────────────────────────────
def main(argv: Sequence[str] | None = None) -> int:
    all_files = _collect_all_py_files(SRC_DIR)

    orphaned_files = check_orphaned_files(all_files)
    orphaned_ports = check_orphaned_ports(all_files)
    adapter_issues = check_adapter_init_consistency()
    mypy_issues = check_pyproject_mypy_overrides()
    compile_issues = check_compile_all(all_files)

    total = len(orphaned_files) + len(orphaned_ports) + len(adapter_issues) + len(mypy_issues) + len(compile_issues)

    print("=" * 70)
    print("CHECK ORPHANS — Dead code & stale reference detector")
    print("=" * 70)

    if orphaned_files:
        print(f"\n🟡 ORPHANED FILES ({len(orphaned_files)}):")
        for path in orphaned_files:
            print(f"   {path}")

    if orphaned_ports:
        print(f"\n🟡 ORPHANED PORTS ({len(orphaned_ports)}):")
        for path in orphaned_ports:
            print(f"   {path}")

    if adapter_issues:
        print(f"\n🟡 ADAPTER INIT ISSUES ({len(adapter_issues)}):")
        for msg in adapter_issues:
            print(f"   {msg}")

    if mypy_issues:
        print(f"\n🟡 PYPYPROJECT OVERRIDES ({len(mypy_issues)}):")
        for msg in mypy_issues:
            print(f"   {msg}")

    if compile_issues:
        print(f"\n🔴 COMPILE ERRORS ({len(compile_issues)}):")
        for msg in compile_issues:
            print(f"   {msg}")

    if total == 0:
        print("\n✅ No orphaned files, stale references, or compile errors found.")
        return 0

    print(f"\n{'=' * 70}")
    print(f"TOTAL ISSUES: {total}")
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main())
