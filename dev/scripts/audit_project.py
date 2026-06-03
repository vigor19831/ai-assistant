#!/usr/bin/env python3
"""audit_project.py — Raw dead code list for AI review.

Just lists everything suspicious. No smart exclusions. No fixes.
You review the list and decide what to delete.

Usage:
    python dev/scripts/audit_project.py          # list everything
    python dev/scripts/audit_project.py --ast    # AST-only (no coverage needed)

Exit: 0=empty list, 1=found something, 2=error
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# ── Config ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "ai_assistant"
TESTS_DIR = PROJECT_ROOT / "dev" / "tests"
COVERAGE_FILE = PROJECT_ROOT / ".coverage"

SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "vendor", "ui", "data", "logs", "tmp", "temp", "ops"}
SKIP_FILES = {"__init__.py"}
# Entry points are never imported inside the package tree — expected orphan behavior
ENTRY_POINT_FILES = {"main.py"}

# Only skip dunder names that Python itself requires
SKIP_NAMES = {"__all__", "__version__"}

# Only skip methods Python runtime calls (cannot be "dead" by definition)
SKIP_METHODS = {
    "__init__", "__new__", "__del__", "__repr__", "__str__", "__bytes__",
    "__format__", "__lt__", "__le__", "__eq__", "__ne__", "__gt__", "__ge__",
    "__hash__", "__bool__", "__getattr__", "__getattribute__", "__setattr__",
    "__delattr__", "__dir__", "__get__", "__set__", "__delete__", "__slots__",
    "__init_subclass__", "__set_name__", "__class_getitem__", "__enter__",
    "__exit__", "__await__", "__aiter__", "__anext__", "__aenter__", "__aexit__",
    "__call__", "__len__", "__getitem__", "__setitem__", "__delitem__",
    "__iter__", "__contains__", "__add__", "__sub__", "__mul__", "__truediv__",
    "__floordiv__", "__mod__", "__pow__", "__and__", "__or__", "__xor__",
    "__lshift__", "__rshift__", "__neg__", "__pos__", "__abs__", "__invert__",
    "__complex__", "__int__", "__float__", "__index__", "__round__", "__trunc__",
    "__floor__", "__ceil__", "__copy__", "__deepcopy__", "__reduce__", "__reduce_ex__",
    "__getstate__", "__setstate__", "__post_init__",
}

RED, YELLOW, GREEN, CYAN, RESET, BOLD = "\033[91m", "\033[93m", "\033[92m", "\033[96m", "\033[0m", "\033[1m"

def color(t: str, c: str) -> str:
    return f"{c}{t}{RESET}"


# ── Coverage ──────────────────────────────────────────────────────────────────
class CoverageAnalyzer:
    def __init__(self, coverage_path: Path):
        self.coverage_path = coverage_path
        self.executed_lines: dict[str, set[int]] = {}
        self._load()

    def _load(self) -> None:
        try:
            import coverage as cov_module
        except ImportError:
            return
        try:
            data = cov_module.CoverageData(str(self.coverage_path))
            data.read()
            for filename in data.measured_files():
                lines = data.lines(filename)
                if lines:
                    self.executed_lines[filename] = set(lines)
        except Exception:
            pass

    def is_live(self, file: Path, line: int) -> bool:
        for key in (str(file), str(file.resolve())):
            if key in self.executed_lines:
                return line in self.executed_lines[key]
        return False

    def has_data(self) -> bool:
        return bool(self.executed_lines)


# ── File / AST helpers ──────────────────────────────────────────────────────
def collect_py(root: Path) -> list[Path]:
    return [f for f in root.rglob("*.py") if not any(p in SKIP_DIRS for p in f.parts)]


def parse_file(p: Path) -> ast.AST | None:
    try:
        return ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


class ImportCollector(ast.NodeVisitor):
    def __init__(self, current_module: str = ""):
        self.imports: set[str] = set()
        self.current = current_module

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level = node.level
        if level > 0 and self.current:
            parts = self.current.split(".")
            base = ".".join(parts[:-level]) if len(parts) >= level else ""
            resolved = f"{base}.{module}".strip(".") if module else base
        else:
            resolved = module
        if resolved:
            self.imports.add(resolved)
        for alias in node.names:
            if resolved:
                self.imports.add(f"{resolved}.{alias.name}")
            self.imports.add(alias.name)


class ReferenceCollector(ast.NodeVisitor):
    """Collect ALL names that appear in code — including method names via attributes."""

    def __init__(self):
        self.refs: set[str] = set()

    def _add_name(self, node: ast.expr) -> None:
        if isinstance(node, ast.Name):
            self.refs.add(node.id)
        elif isinstance(node, ast.Call):
            self._add_name(node.func)
        elif isinstance(node, ast.Attribute):
            self.refs.add(node.attr)
            if isinstance(node.value, ast.Name):
                self.refs.add(node.value.id)
            elif isinstance(node.value, ast.Attribute):
                self._add_name(node.value)

    def visit_Name(self, node: ast.Name) -> None:
        self.refs.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.refs.add(node.attr)
        if isinstance(node.value, ast.Name):
            self.refs.add(node.value.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._add_name(node.func)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for dec in node.decorator_list:
            self._add_name(dec)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        for dec in node.decorator_list:
            self._add_name(dec)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for dec in node.decorator_list:
            self._add_name(dec)
        self.generic_visit(node)


class DefinitionCollector(ast.NodeVisitor):
    """Collect ALL definitions — functions, classes, methods, variables."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.defs: dict[str, tuple[str, int]] = {}  # top-level name -> (kind, line)
        self.methods: dict[str, dict[str, int]] = {}  # class -> {method: line}
        self.all_names: set[str] = set()
        self.classes: dict[str, tuple[int, list[str]]] = {}  # name -> (line, bases)
        self.exports: set[str] = set()
        self._class_stack: list[str] = []

    def _get_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_name(node.value) + "." + node.attr
        return ""

    def _get_bases(self, node: ast.ClassDef) -> list[str]:
        return [self._get_name(b) for b in node.bases]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.all_names.add(node.name)
        if self._class_stack:
            # Inside class — it's a method, handled by visit_ClassDef
            pass
        elif not node.name.startswith("_") and node.name != "main":
            self.defs[node.name] = ("function", node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.all_names.add(node.name)
        if self._class_stack:
            pass
        elif not node.name.startswith("_") and node.name != "main":
            self.defs[node.name] = ("async function", node.lineno)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.all_names.add(node.name)
        self.classes[node.name] = (node.lineno, self._get_bases(node))
        if not node.name.startswith("_"):
            self.defs[node.name] = ("class", node.lineno)

        self.methods[node.name] = {}
        self._class_stack.append(node.name)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.all_names.add(item.name)
                if item.name not in SKIP_METHODS and not item.name.startswith("_"):
                    self.methods[node.name][item.name] = item.lineno
            elif isinstance(item, ast.ClassDef):
                self.visit(item)
            else:
                self.visit(item)
        self._class_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.all_names.add(target.id)
                if not target.id.startswith("_") and target.id not in SKIP_NAMES:
                    self.defs[target.id] = ("variable", node.lineno)


# ── Registry ─────────────────────────────────────────────────────────────────
def build_registry(all_files: list[Path]) -> dict[str, dict]:
    registry: dict[str, dict] = {}
    for f in all_files:
        rel = f.relative_to(SRC_DIR.parent)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = Path(parts[-1]).stem
        mod = ".".join(parts)

        tree = parse_file(f)
        if tree is None:
            continue

        ic = ImportCollector(mod)
        ic.visit(tree)

        rc = ReferenceCollector()
        rc.visit(tree)

        dc = DefinitionCollector(f)
        dc.visit(tree)

        exports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    exports.add(elt.value)

        registry[mod] = {
            "file": f,
            "imports": ic.imports,
            "refs": rc.refs | exports,
            "defs": dc.defs,
            "methods": dc.methods,
            "all_names": dc.all_names,
            "classes": dc.classes,
            "exports": exports,
        }
    return registry


# ── Checks (raw, no exclusions) ───────────────────────────────────────────────
def find_orphaned_files(registry: dict) -> list[tuple[Path, str]]:
    all_imports: set[str] = set()
    for info in registry.values():
        all_imports.update(info["imports"])

    orphaned = []
    for mod, info in registry.items():
        f = info["file"]
        if f.name in SKIP_FILES:
            continue
        if f.name in ENTRY_POINT_FILES:
            continue
        found = any(
            imp == mod or imp.startswith(f"{mod}.") or imp == f.stem
            for imp in all_imports
        )
        if not found:
            orphaned.append((f, "never imported"))
    return orphaned


def find_unused_symbols(registry: dict, coverage: CoverageAnalyzer | None = None) -> list[tuple[Path, str, str, int]]:
    global_refs: set[str] = set()
    for info in registry.values():
        global_refs.update(info["refs"])

    unused = []
    for mod, info in registry.items():
        f = info["file"]
        for name, (kind, line) in info["defs"].items():
            if name in SKIP_NAMES:
                continue
            if name in global_refs:
                continue
            if name in info["exports"]:
                continue
            # In coverage mode: skip local variables (kind == "variable"), only report top-level symbols
            if coverage is not None and kind == "variable":
                continue
            # In coverage mode: check if line was executed
            if coverage is not None and coverage.is_live(f, line):
                continue
            unused.append((f, name, kind, line))
    return unused


def find_unused_methods(registry: dict, coverage: CoverageAnalyzer | None = None) -> list[tuple[Path, str, str, int]]:
    unused = []
    for mod, info in registry.items():
        f = info["file"]
        for cls_name, methods in info["methods"].items():
            for method, line in methods.items():
                # In coverage mode: skip if line was executed
                if coverage is not None and coverage.is_live(f, line):
                    continue
                found = method in info["refs"]
                if not found:
                    for other_mod, other_info in registry.items():
                        if other_mod == mod:
                            continue
                        if method in other_info["refs"]:
                            found = True
                            break
                if not found:
                    unused.append((f, f"{cls_name}.{method}", "method", line))
    return unused


def find_dead_constants(registry: dict) -> list[tuple[Path, str, int]]:
    dead = []
    for mod, info in registry.items():
        f = info["file"]
        for name, (kind, line) in info["defs"].items():
            if kind == "variable" and name.isupper() and name not in info["refs"]:
                found = any(name in other["refs"] for other in registry.values())
                if not found:
                    dead.append((f, name, line))
    return dead


def find_duplicate_blocks(registry: dict, min_lines: int = 8) -> list[tuple[Path, Path, int, int]]:
    if not hasattr(ast, "unparse"):
        return []

    blocks: dict[str, list[tuple[Path, int]]] = {}
    for mod, info in registry.items():
        f = info["file"]
        tree = parse_file(f)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                try:
                    source = ast.unparse(node)
                except Exception:
                    continue
                lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
                if len(lines) >= min_lines:
                    h = hashlib.md5("\n".join(lines).encode()).hexdigest()[:16]
                    blocks.setdefault(h, []).append((f, node.lineno))

    duplicates = []
    seen = set()
    for h, locations in blocks.items():
        if len(locations) > 1:
            for i, (f1, line1) in enumerate(locations):
                for f2, line2 in locations[i + 1:]:
                    if f1 == f2:
                        continue
                    key = tuple(sorted([str(f1), str(f2)]))
                    if key not in seen:
                        seen.add(key)
                        duplicates.append((f1, f2, line1, line2))
    return duplicates


def check_stale_pyproject() -> list[str]:
    issues = []
    pp = PROJECT_ROOT / "pyproject.toml"
    if not pp.exists():
        return issues
    try:
        import tomllib
        with pp.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:
        return [f"Cannot parse pyproject.toml: {exc}"]

    for override in data.get("tool", {}).get("mypy", {}).get("overrides", []):
        for mod in override.get("module", []):
            if "*" in mod:
                continue
            parts = mod.split(".")
            rel = parts[1:] if parts[0] == "ai_assistant" else parts
            if not rel:
                continue
            fp = SRC_DIR
            for p in rel[:-1]:
                fp = fp / p
            if not (fp / (rel[-1] + ".py")).exists() and not (fp / rel[-1] / "__init__.py").exists():
                issues.append(f"mypy override '{mod}' -> file not found")
    return issues


def check_cycles(registry: dict) -> list[str]:
    cycles = []
    checked = set()
    for mod, info in registry.items():
        for imp in info["imports"]:
            if imp in registry:
                other = registry[imp]
                if mod in other["imports"]:
                    pair = tuple(sorted([mod, imp]))
                    if pair not in checked:
                        checked.add(pair)
                        cycles.append(f"{pair[0]} <-> {pair[1]}")
    return cycles


def check_empty_dirs(root: Path) -> list[Path]:
    return [d for d in sorted(root.rglob("*")) if d.is_dir() and d != root and not any(d.iterdir())]


# ── Report (raw list) ────────────────────────────────────────────────────────
def report(orphaned, unused, dead_methods, dead_consts, duplicates, stale, cycles, empty, mode: str) -> int:
    total = len(orphaned) + len(unused) + len(dead_methods) + len(dead_consts) + len(duplicates) + len(stale) + len(cycles) + len(empty)

    print()
    print("=" * 70)
    print(color("POTENTIAL DEAD CODE — REVIEW LIST", BOLD + CYAN))
    print("=" * 70)
    print(f"Mode: {mode}")
    print("Copy this list to AI chat and ask: 'Which of these can I delete?'")
    print()

    sections = [
        (orphaned, "ORPHANED FILES (never imported)"),
        (unused, "UNUSED SYMBOLS (defined but never referenced)"),
        (dead_methods, "UNUSED METHODS (never called)"),
        (dead_consts, "DEAD CONSTANTS (UPPER_CASE, never used)"),
        (duplicates, "DUPLICATE CODE BLOCKS"),
        (stale, "STALE PYPROJECT REFERENCES"),
        (cycles, "CIRCULAR IMPORTS"),
        (empty, "EMPTY DIRECTORIES"),
    ]

    for items, label in sections:
        if items:
            print(f"\n{color(label, BOLD)} ({len(items)}):")
            for item in items:
                if len(item) == 2:
                    f, reason = item
                    rel = f.relative_to(PROJECT_ROOT)
                    print(f"  {rel}  — {reason}")
                elif len(item) == 3:
                    f, name, line = item
                    rel = f.relative_to(PROJECT_ROOT)
                    print(f"  {rel}:{line}  — {name}")
                elif len(item) == 4 and isinstance(item[0], Path):
                    f, name, kind, line = item
                    rel = f.relative_to(PROJECT_ROOT)
                    print(f"  {rel}:{line}  — {kind} {name}")
                elif len(item) == 4:
                    f1, f2, l1, l2 = item
                    r1 = f1.relative_to(PROJECT_ROOT)
                    r2 = f2.relative_to(PROJECT_ROOT)
                    print(f"  {r1}:{l1} ~ {r2}:{l2}")
                else:
                    print(f"  {item}")

    if total == 0:
        print(f"\n{color('Nothing found. Project looks clean.', GREEN)}")
        return 0

    print(f"\n{color(f'TOTAL ITEMS TO REVIEW: {total}', BOLD)}")
    print("=" * 70)
    return 1


# ── Main ─────────────────────────────────────────────────────────────────────
def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Raw dead code list for AI review")
    parser.add_argument("--ast", action="store_true", help="Force AST-only (ignore coverage)")
    parser.add_argument("--coverage-file", type=Path, default=COVERAGE_FILE, help="Path to .coverage")
    args = parser.parse_args(argv)

    if not SRC_DIR.exists():
        print(color("ERROR: src/ai_assistant not found", RED))
        return 2

    # Coverage check
    cov = CoverageAnalyzer(args.coverage_file)
    use_coverage = cov.has_data() and not args.ast

    if use_coverage:
        mode = "COVERAGE (executed lines)"
        print(color(f"Coverage: {len(cov.executed_lines)} files", GREEN))
    else:
        mode = "AST (static analysis)"
        if args.ast:
            print(color("AST mode forced", YELLOW))
        else:
            print(color("No coverage data. Run: pytest --cov", YELLOW))

    print(color("Building registry...", CYAN), end=" ")
    all_src = collect_py(SRC_DIR)
    registry = build_registry(all_src)
    print(color(f"{len(registry)} modules", GREEN))

    print(color("Checking orphaned files...", CYAN), end=" ")
    orphaned = find_orphaned_files(registry)
    print(color(f"{len(orphaned)}", GREEN))

    print(color("Checking unused symbols...", CYAN), end=" ")
    unused = find_unused_symbols(registry, cov if use_coverage else None)
    print(color(f"{len(unused)}", GREEN))

    print(color("Checking unused methods...", CYAN), end=" ")
    dead_methods = find_unused_methods(registry, cov if use_coverage else None)
    print(color(f"{len(dead_methods)}", GREEN))

    print(color("Checking dead constants...", CYAN), end=" ")
    dead_consts = find_dead_constants(registry)
    print(color(f"{len(dead_consts)}", GREEN))

    print(color("Checking duplicates...", CYAN), end=" ")
    duplicates = find_duplicate_blocks(registry)
    print(color(f"{len(duplicates)}", GREEN))

    print(color("Checking pyproject.toml...", CYAN), end=" ")
    stale = check_stale_pyproject()
    print(color(f"{len(stale)}", GREEN))

    print(color("Checking circular imports...", CYAN), end=" ")
    cycles = check_cycles(registry)
    print(color(f"{len(cycles)}", GREEN))

    print(color("Checking empty dirs...", CYAN), end=" ")
    empty = check_empty_dirs(SRC_DIR)
    print(color(f"{len(empty)}", GREEN))

    return report(orphaned, unused, dead_methods, dead_consts, duplicates, stale, cycles, empty, mode)


if __name__ == "__main__":
    sys.exit(main())
