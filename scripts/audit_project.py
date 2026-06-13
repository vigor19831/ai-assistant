#!/usr/bin/env python3
"""audit_project.py — Domain-aware dead code audit.

Understands framework registration patterns:
  @router.post("/path")  ->  function is used by FastAPI
  @step("name")          ->  function is used by pipeline registry
  @register("port", "name") ->  adapter is used by factory

Usage:
    python scripts/audit_project.py          # interactive mode selection
    python scripts/audit_project.py --ast    # AST-only, no interactivity
    python scripts/audit_project.py --auto   # skip interactive, use defaults

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
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "ai_assistant"
COVERAGE_FILE = PROJECT_ROOT / ".coverage"

SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "vendor", "ui", "data", "logs", "tmp", "temp", "ops"}
SKIP_FILES = {"__init__.py"}
ENTRY_POINT_FILES = {"main.py"}
SKIP_NAMES = {"__all__", "__version__"}
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

# ── Domain-aware registration patterns ───────────────────────────────────────
# These decorators mark functions/classes as "used by framework".
# The script extracts registered names and treats them as referenced.
REGISTRATION_DECORATORS: dict[str, tuple[str, ...]] = {
    # FastAPI router registration
    "router": ("get", "post", "put", "delete", "patch", "head", "options", "websocket"),
    "APIRouter": ("get", "post", "put", "delete", "patch", "head", "options", "websocket"),
    # Pipeline step registration
    "step": ("step",),
    # Adapter factory registration
    "register": ("register",),
    # App-level decorators (if used)
    "app": ("get", "post", "put", "delete", "patch"),
    "FastAPI": ("get", "post", "put", "delete", "patch"),
}

# Router variable name patterns (prefix-based to avoid hardcoding)
ROUTER_VARIABLE_PREFIXES = ("router", "admin_router", "api_router")

# ABC base classes that define port contracts — their methods are required
ABC_BASES = {"ABC", "IChunker", "IEmbedder", "ILLM", "IReranker", "IVectorStore",
             "IChatStorage", "ISettingsStorage", "IClosable", "IInitializable",
             "ITool", "IToolRegistry"}

# Framework base classes whose methods are callbacks (not called by user code)
FRAMEWORK_BASES = {"BaseHTTPMiddleware", "BaseMiddleware", "Middleware"}

# Framework callback methods that are never called by user code directly.
# Only skipped when the class inherits from FRAMEWORK_BASES.
FRAMEWORK_CALLBACKS = frozenset({"dispatch", "lifespan"})


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


# ── Interactive prompt ───────────────────────────────────────────────────────
def ask_mode(cov: CoverageAnalyzer) -> bool:
    """Single question: AST or Coverage."""
    print()
    print("  AUDIT PROJECT")
    print("  " + "-" * 36)
    print()

    ast_label = "AST-only   (static analysis)"
    if cov.has_data():
        cov_label = f"Coverage   (data: {len(cov.executed_lines)} files)"
        default = "2"
    else:
        cov_label = "Coverage   (no .coverage -- run pytest --cov)"
        default = "1"

    print(f"  [1]  {ast_label}")
    print(f"  [2]  {cov_label}")
    print()

    while True:
        try:
            choice = input(f"  Mode [1/2] (default {default}): ").strip() or default
        except (EOFError, KeyboardInterrupt):
            print("\n  ! Interrupted -- switching to AST")
            return True
        if choice == "1":
            print("  -> AST-only")
            return True
        if choice == "2":
            if not cov.has_data():
                print("  ! No coverage data -- switching to AST")
                return True
            print("  -> Coverage-based")
            return False
        print("  ! Enter 1 or 2")


# ── Progress helper ──────────────────────────────────────────────────────────
def _check(label: str, items: list) -> list:
    """Print progress line and return result."""
    count = len(items)
    sym = "ok" if count == 0 else f"{count} found"
    print(f"  *  {label:<36} {sym}")
    return items


# ── File / AST helpers ──────────────────────────────────────────────────────
def collect_py(root: Path) -> list[Path]:
    return [
        f for f in root.rglob("*.py")
        if f.name not in SKIP_FILES and not any(p in SKIP_DIRS for p in f.parts)
    ]


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


class RegistrationCollector(ast.NodeVisitor):
    """Extract names of functions/classes registered via framework decorators.

    Examples:
        @router.post("/chat")  ->  registers 'chat' function
        @router_oai.get("/v1/models") -> registers 'list_models' function
        @step("embed_query")   ->  registers 'embed_query' function
        @register("llm", "mock") -> registers 'MockLLM' class
    """

    def __init__(self):
        self.registered_names: set[str] = set()
        self.registered_modules: set[str] = set()

    def _get_decorator_name(self, node: ast.expr) -> str:
        """Get decorator name like 'router.post' or 'step'."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_decorator_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return ""

    def _is_router_variable(self, name: str) -> bool:
        """Check if name matches router variable patterns (prefix-based)."""
        return any(name == prefix or name.startswith(prefix + "_") for prefix in ROUTER_VARIABLE_PREFIXES)

    def _is_registration_decorator(self, name: str) -> bool:
        """Check if decorator name matches known registration patterns."""
        parts = name.split(".")
        if len(parts) == 2:
            base, method = parts
            # Check known decorator classes
            if base in REGISTRATION_DECORATORS:
                return method in REGISTRATION_DECORATORS[base]
            # Check router variable names (router_oai.get, etc.)
            if self._is_router_variable(base):
                return method in ("get", "post", "put", "delete", "patch", "head", "options", "websocket")
        if len(parts) == 1:
            return parts[0] in REGISTRATION_DECORATORS
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_decorators(node, node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_decorators(node, node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._check_decorators(node, node.name)
        self.generic_visit(node)

    def _check_decorators(self, node: ast.AST, name: str) -> None:
        if not hasattr(node, "decorator_list"):
            return
        for dec in node.decorator_list:
            dec_name = self._get_decorator_name(dec)
            if self._is_registration_decorator(dec_name):
                self.registered_names.add(name)
                self.registered_modules.add("")


class DefinitionCollector(ast.NodeVisitor):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.defs: dict[str, tuple[str, int]] = {}
        self.methods: dict[str, dict[str, int]] = {}
        self.classes: dict[str, tuple[int, list[str]]] = {}
        self.exports: set[str] = set()
        self._class_stack: list[str] = []
        self.has_registration_decorator: bool = False

    def _get_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_name(node.value) + "." + node.attr
        return ""

    def _get_bases(self, node: ast.ClassDef) -> list[str]:
        return [self._get_name(b) for b in node.bases]

    def _check_registration_decorator(self, node: ast.AST) -> None:
        """Check if any decorator is a registration decorator."""
        if not hasattr(node, "decorator_list"):
            return
        rc = RegistrationCollector()
        for dec in node.decorator_list:
            dec_name = rc._get_decorator_name(dec)
            if rc._is_registration_decorator(dec_name):
                self.has_registration_decorator = True
                break

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_registration_decorator(node)
        if self._class_stack:
            pass
        elif not node.name.startswith("_") and node.name != "main":
            self.defs[node.name] = ("function", node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_registration_decorator(node)
        if self._class_stack:
            pass
        elif not node.name.startswith("_") and node.name != "main":
            self.defs[node.name] = ("async function", node.lineno)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._check_registration_decorator(node)
        self.classes[node.name] = (node.lineno, self._get_bases(node))
        if not node.name.startswith("_"):
            self.defs[node.name] = ("class", node.lineno)

        self.methods[node.name] = {}
        self._class_stack.append(node.name)
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
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
                if not target.id.startswith("_") and target.id not in SKIP_NAMES:
                    self.defs[target.id] = ("variable", node.lineno)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        if not elt.id.startswith("_") and elt.id not in SKIP_NAMES:
                            self.defs[elt.id] = ("variable", node.lineno)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            if not node.target.id.startswith("_") and node.target.id not in SKIP_NAMES:
                self.defs[node.target.id] = ("variable", node.lineno)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        if isinstance(node.target, ast.Name):
            if not node.target.id.startswith("_") and node.target.id not in SKIP_NAMES:
                self.defs[node.target.id] = ("variable", node.lineno)


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

        regc = RegistrationCollector()
        regc.visit(tree)

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
            "tree": tree,
            "imports": ic.imports,
            "refs": rc.refs | exports | regc.registered_names,
            "registered_names": regc.registered_names,
            "defs": dc.defs,
            "methods": dc.methods,
            "classes": dc.classes,
            "exports": exports,
            "has_registration_decorator": dc.has_registration_decorator,
        }
    return registry


# ── Checks ───────────────────────────────────────────────────────────────────
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
        # File is not orphaned if it has registration decorators (exports via framework)
        if info["has_registration_decorator"]:
            continue
        # File is not orphaned if it exports symbols in __all__
        if info["exports"]:
            continue
        found = any(
            imp == mod or imp.startswith(f"{mod}.") or imp == f.stem
            for imp in all_imports
        )
        if not found:
            orphaned.append((f, "never imported"))
    return orphaned


def find_unused_symbols(registry: dict) -> list[tuple[Path, str, str, int]]:
    global_refs: set[str] = set()
    for info in registry.values():
        global_refs.update(info["refs"])

    unused = []
    for mod, info in registry.items():
        f = info["file"]
        for name, (kind, line) in info["defs"].items():
            if name in SKIP_NAMES:
                continue
            # Registered names are considered used
            if name in info["registered_names"]:
                continue
            if name in global_refs:
                continue
            if name in info["exports"]:
                continue
            unused.append((f, name, kind, line))
    return unused


def _is_framework_class(bases: list[str]) -> bool:
    """Check if class inherits from a framework base (has framework callbacks)."""
    return any(base in FRAMEWORK_BASES for base in bases)


def _is_abc_class(bases: list[str]) -> bool:
    """Check if class inherits from an ABC port (has contract-required methods)."""
    return any(base in ABC_BASES for base in bases)


def find_unused_methods(registry: dict) -> list[tuple[Path, str, str, int]]:
    unused = []
    for mod, info in registry.items():
        f = info["file"]
        for cls_name, methods in info["methods"].items():
            bases = info["classes"].get(cls_name, (0, []))[1]

            # Skip ABC port classes — methods are contract-required
            if _is_abc_class(bases):
                continue

            # Skip framework classes — framework callbacks are not user-called
            is_framework = _is_framework_class(bases)

            for method, line in methods.items():
                # Framework callbacks (dispatch, lifespan) are not unused
                if is_framework and method in FRAMEWORK_CALLBACKS:
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
                if name in info["exports"]:
                    continue
                found = any(name in other["refs"] for other in registry.values())
                if not found:
                    dead.append((f, name, line))
    return dead


def find_duplicate_blocks(registry: dict, min_lines: int = 5) -> list[tuple[Path, Path, int, int]]:
    if not hasattr(ast, "unparse"):
        return []

    blocks: dict[str, list[tuple[Path, int]]] = {}
    for mod, info in registry.items():
        f = info["file"]
        tree = info.get("tree")
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
        raw_modules = override.get("module", [])
        modules = [raw_modules] if isinstance(raw_modules, str) else raw_modules
        for mod in modules:
            if "*" in mod:
                continue
            parts = mod.split(".")
            rel = parts[1:] if parts[0] == "ai_assistant" else parts
            if not rel:
                continue
            fp = SRC_DIR
            for p in rel[:-1]:
                fp = fp / p
            file_candidate = fp / (rel[-1] + ".py")
            pkg_candidate = fp / rel[-1] / "__init__.py"
            if not file_candidate.exists() and not pkg_candidate.exists():
                issues.append(f"mypy override '{mod}' -> file not found")
    return issues


def check_cycles(registry: dict) -> list[str]:
    """Detect import cycles via DFS. Each unique cycle reported once."""
    cycles: list[str] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def _normalize(cycle_nodes: list[str]) -> tuple[str, ...]:
        if not cycle_nodes:
            return tuple()
        nodes = cycle_nodes[:-1] if cycle_nodes[0] == cycle_nodes[-1] else list(cycle_nodes)
        if not nodes:
            return tuple()
        n = len(nodes)
        return min(tuple(nodes[i:] + nodes[:i]) for i in range(n))

    def dfs(node: str, path: list[str]) -> None:
        for imp in registry[node]["imports"]:
            if imp not in registry:
                continue
            if imp in path:
                idx = path.index(imp)
                cycle = path[idx:] + [imp]
                key = _normalize(cycle)
                if key and key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(" -> ".join(cycle))
                continue
            if len(path) < 8:
                dfs(imp, path + [imp])

    for mod in registry:
        dfs(mod, [mod])

    return cycles


def check_empty_dirs(root: Path) -> list[tuple[Path, str]]:
    empty = []
    for d in sorted(root.rglob("*")):
        if not d.is_dir() or d == root:
            continue
        try:
            if not any(d.iterdir()):
                empty.append((d, "empty"))
        except OSError:
            pass
    return empty


# ── Report ───────────────────────────────────────────────────────────────────
def report(orphaned, unused, dead_methods, dead_consts, duplicates, stale, cycles, empty, mode: str) -> int:
    total = len(orphaned) + len(unused) + len(dead_methods) + len(dead_consts) + len(duplicates) + len(stale) + len(cycles) + len(empty)

    print()
    print(f"  DEAD CODE AUDIT  |  {mode}")
    print("  " + "-" * 40)
    print("  This script DETECTS potential issues. Manual review required.")
    print("  " + "-" * 40)

    sections = [
        (orphaned, "Orphaned files"),
        (unused, "Unused symbols"),
        (dead_methods, "Unused methods"),
        (dead_consts, "Dead constants"),
        (duplicates, "Duplicate blocks"),
        (stale, "Stale pyproject refs"),
        (cycles, "Circular imports"),
        (empty, "Empty directories"),
    ]

    for items, label in sections:
        if items:
            print(f"\n  {label}  ({len(items)}):")
            for item in items:
                if len(item) == 2 and isinstance(item[0], Path):
                    f, reason = item
                    rel = f.relative_to(PROJECT_ROOT)
                    print(f"    {rel}  -- {reason}")
                elif len(item) == 3:
                    f, name, line = item
                    rel = f.relative_to(PROJECT_ROOT)
                    print(f"    {rel}:{line}  -- {name}")
                elif len(item) == 4 and isinstance(item[1], str):
                    f, name, kind, line = item
                    rel = f.relative_to(PROJECT_ROOT)
                    print(f"    {rel}:{line}  -- {kind} {name}")
                elif len(item) == 4 and isinstance(item[1], Path):
                    f1, f2, l1, l2 = item
                    r1 = f1.relative_to(PROJECT_ROOT)
                    r2 = f2.relative_to(PROJECT_ROOT)
                    print(f"    {r1}:{l1} ~ {r2}:{l2}")
                else:
                    print(f"    {item}")

    print()
    if total == 0:
        print("  [OK] No suspicious code detected.")
        print("  Note: This is static analysis. Runtime usage may differ.")
        return 0

    print(f"  [!] {total} item(s) detected for manual review.")
    print("  Action: Review each item. Remove if truly unused, or document why kept.")
    return 1


# ── Main ─────────────────────────────────────────────────────────────────────
def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Domain-aware dead code audit")
    parser.add_argument("--ast", action="store_true", help="AST-only (ignore coverage)")
    parser.add_argument("--coverage-file", type=Path, default=COVERAGE_FILE, help="Path to .coverage")
    parser.add_argument("--auto", action="store_true", help="Skip interactive, use defaults")
    args = parser.parse_args(argv)

    if not SRC_DIR.exists():
        print("  [ERR] src/ai_assistant not found")
        return 2

    cov = CoverageAnalyzer(args.coverage_file)

    if args.ast or args.auto:
        use_ast = args.ast
        if args.auto and not args.ast and not cov.has_data():
            use_ast = True
    else:
        use_ast = ask_mode(cov)

    mode = "AST" if use_ast else "Coverage"

    print()
    print("  Scanning...")
    print()

    all_src = collect_py(SRC_DIR)
    registry = build_registry(all_src)
    print(f"  *  Registry built                         {len(registry)} modules")

    orphaned = _check("Orphaned files",       find_orphaned_files(registry))
    unused   = _check("Unused symbols",       find_unused_symbols(registry))
    methods  = _check("Unused methods",       find_unused_methods(registry))
    consts   = _check("Dead constants",       find_dead_constants(registry))
    dups     = _check("Duplicate blocks",     find_duplicate_blocks(registry, min_lines=5))
    stale    = _check("Stale pyproject refs", check_stale_pyproject())
    cycles   = _check("Circular imports",     check_cycles(registry))
    empty    = _check("Empty directories",    check_empty_dirs(SRC_DIR))

    return report(orphaned, unused, methods, consts, dups, stale, cycles, empty, mode)


if __name__ == "__main__":
    sys.exit(main())
