#!/usr/bin/env python3
"""check_all.py — Unified project validation.

Universally checks any Python project with standard tools:
- ruff (lint)
- mypy (types)
- pytest + coverage (tests + branch coverage)
- coverage audit (analyzes .coverage JSON for low coverage)
- AST audit (dead code, duplicates, cycles via ast module)

Usage:
    python scripts/check_all.py         # interactive menu
    python scripts/check_all.py 1       # tests only
    python scripts/check_all.py 5       # full check
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# ── Config ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
COVERAGE_FILE = ROOT / ".coverage"

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

ROUTER_VARIABLE_PREFIXES = ("router", "admin_router", "api_router")
ABC_BASES = {"ABC", "IChunker", "IEmbedder", "ILLM", "IReranker", "IVectorStore",
             "IChatStorage", "ISettingsStorage", "IClosable", "IInitializable",
             "ITool", "IToolRegistry"}
FRAMEWORK_BASES = {"BaseHTTPMiddleware", "BaseMiddleware", "Middleware"}
FRAMEWORK_CALLBACKS = frozenset({"dispatch", "lifespan"})


# ── Auto-Logging to Root (always on) ────────────────────────────────────────

class TeeOutput:
    """Redirects stdout/stderr to both console and a log file in project root."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_file = open(log_path, "w", encoding="utf-8")
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        self._lock = threading.Lock()

    def write(self, data: str) -> int:
        with self._lock:
            self._stdout.write(data)
            self._stdout.flush()
            self.log_file.write(data)
            self.log_file.flush()
        return len(data)

    def flush(self) -> None:
        with self._lock:
            self._stdout.flush()
            self.log_file.flush()

    def isatty(self) -> bool:
        return self._stdout.isatty()

    def fileno(self) -> int:
        return self._stdout.fileno()

    def close(self) -> None:
        self.log_file.close()

    def __enter__(self):
        sys.stdout = self
        sys.stderr = self
        return self

    def __exit__(self, *args):
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        self.close()


def setup_logging() -> TeeOutput:
    """Setup logging to file in project root. Always active."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = ROOT / f"check_all_{timestamp}.log"
    return TeeOutput(log_path)


# ── Universal AST Audit (inline, no external deps) ──────────────────────────

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

    def visit_Name(self, node: ast.Name) -> None:
        self.refs.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.refs.add(node.attr)
        if isinstance(node.value, ast.Name):
            self.refs.add(node.value.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.refs.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.refs.add(node.func.attr)
            if isinstance(node.func.value, ast.Name):
                self.refs.add(node.func.value.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                self.refs.add(dec.id)
            elif isinstance(dec, ast.Attribute):
                self.refs.add(dec.attr)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                self.refs.add(dec.id)
            elif isinstance(dec, ast.Attribute):
                self.refs.add(dec.attr)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                self.refs.add(dec.id)
            elif isinstance(dec, ast.Attribute):
                self.refs.add(dec.attr)
        self.generic_visit(node)


class RegistrationCollector(ast.NodeVisitor):
    def __init__(self):
        self.registered_names: set[str] = set()

    def _get_decorator_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_decorator_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return ""

    def _is_router_variable(self, name: str) -> bool:
        return any(name == prefix or name.startswith(prefix + "_") for prefix in ROUTER_VARIABLE_PREFIXES)

    def _is_registration_decorator(self, name: str) -> bool:
        parts = name.split(".")
        if len(parts) == 2:
            base, method = parts
            if base in {"router", "APIRouter", "app", "FastAPI", "step", "register"}:
                return method in {"get", "post", "put", "delete", "patch", "head", "options", "websocket", "step", "register"}
            if self._is_router_variable(base):
                return method in {"get", "post", "put", "delete", "patch", "head", "options", "websocket"}
        if len(parts) == 1:
            return parts[0] in {"step", "register"}
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


def build_registry(all_files: list[Path]) -> dict[str, dict]:
    registry: dict[str, dict] = {}
    for f in all_files:
        rel = f.relative_to(SRC.parent)
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
        if info["has_registration_decorator"]:
            continue
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
            if name in info["registered_names"]:
                continue
            if name in global_refs:
                continue
            if name in info["exports"]:
                continue
            unused.append((f, name, kind, line))
    return unused


def _is_framework_class(bases: list[str]) -> bool:
    return any(base in FRAMEWORK_BASES for base in bases)


def _is_abc_class(bases: list[str]) -> bool:
    return any(base in ABC_BASES for base in bases)


def find_unused_methods(registry: dict) -> list[tuple[Path, str, str, int]]:
    unused = []
    for mod, info in registry.items():
        f = info["file"]
        for cls_name, methods in info["methods"].items():
            bases = info["classes"].get(cls_name, (0, []))[1]
            if _is_abc_class(bases):
                continue
            is_framework = _is_framework_class(bases)
            for method, line in methods.items():
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


def check_cycles(registry: dict) -> list[str]:
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


def run_ast_audit(src_dir: Path) -> tuple[list, list, list, list, list, list]:
    all_src = collect_py(src_dir)
    registry = build_registry(all_src)
    orphaned = find_orphaned_files(registry)
    unused = find_unused_symbols(registry)
    methods = find_unused_methods(registry)
    consts = find_dead_constants(registry)
    dups = find_duplicate_blocks(registry, min_lines=5)
    cycles = check_cycles(registry)
    return orphaned, unused, methods, consts, dups, cycles


# ── Coverage Audit ──────────────────────────────────────────────────────────

def run_coverage_audit() -> list[tuple[str, float, str]]:
    """Analyze .coverage file and return low-coverage files."""
    if not COVERAGE_FILE.exists():
        return [("No .coverage file found — run tests first", 0.0, "ERROR")]

    json_path = ROOT / "coverage_audit_temp.json"
    try:
        result = subprocess.run([
            sys.executable, "-m", "coverage", "json",
            "-o", str(json_path),
            "--pretty-print",
        ], cwd=ROOT, capture_output=True, text=True)

        if result.returncode != 0 or not json_path.exists():
            return [("Failed to generate coverage JSON", 0.0, f"ERROR: {result.stderr[:200]}")]

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return [("Exception during coverage audit", 0.0, f"ERROR: {exc}")]
    finally:
        json_path.unlink(missing_ok=True)

    issues = []
    for filename, info in data.get("files", {}).items():
        rel = filename.replace(str(ROOT), "").replace("\\", "/").lstrip("/")
        if not rel.startswith("src/"):
            continue

        summary = info.get("summary", {})
        percent = summary.get("percent_covered", 0)
        branches = summary.get("num_branches", 0)
        missing_branches = summary.get("missing_branches", 0)

        if percent < 50:
            issues.append((rel, percent, "CRITICAL: <50% coverage"))
        elif percent < 70:
            issues.append((rel, percent, "WARNING: <70% coverage"))
        elif branches > 0 and missing_branches / branches > 0.3:
            issues.append((rel, percent, f"BRANCHES: {missing_branches}/{branches} missed"))

    issues.sort(key=lambda x: x[1])
    return issues


# ── Menu & Runner ───────────────────────────────────────────────────────────

def _run_cmd(cmd: list[str], desc: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {desc}")
    print(f"{'='*60}")

    # Fix hanging: non-interactive, unbuffered, no stdin
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTEST_CURRENT_TEST"] = ""
    # Prevent pytest from trying to use terminal features
    env["TERM"] = "dumb"
    env["PY_COLORS"] = "0"
    # Force pytest to not use any interactive features
    env["CI"] = "true"

    # Use Popen with streaming to avoid PIPE deadlock on Windows
    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,  # Line buffered
    )

    # Stream output in real-time to prevent PIPE buffer deadlock
    if process.stdout:
        for line in iter(process.stdout.readline, ''):
            sys.stdout.write(line)
            sys.stdout.flush()
        process.stdout.close()

    returncode = process.wait()

    if returncode == 0:
        print(f"\n  [OK] {desc}")
        return True
    else:
        print(f"\n  [FAIL] {desc}")
        return False


def _show_ast_results(orphaned, unused, methods, consts, dups, cycles):
    print(f"\n{'='*60}")
    print("  AST AUDIT RESULTS")
    print(f"{'='*60}")

    sections = [
        (orphaned, "Orphaned files"),
        (unused, "Unused symbols"),
        (methods, "Unused methods"),
        (consts, "Dead constants"),
        (dups, "Duplicate blocks"),
        (cycles, "Circular imports"),
    ]

    total = 0
    for items, label in sections:
        if items:
            total += len(items)
            print(f"\n  {label}  ({len(items)}):")
            for item in items:
                if len(item) == 2:
                    f, reason = item
                    rel = f.relative_to(ROOT)
                    print(f"    {rel}  -- {reason}")
                elif len(item) == 3:
                    f, name, line = item
                    rel = f.relative_to(ROOT)
                    print(f"    {rel}:{line}  -- {name}")
                elif len(item) == 4 and isinstance(item[1], str):
                    f, name, kind, line = item
                    rel = f.relative_to(ROOT)
                    print(f"    {rel}:{line}  -- {kind} {name}")
                elif len(item) == 4 and isinstance(item[1], Path):
                    f1, f2, l1, l2 = item
                    r1 = f1.relative_to(ROOT)
                    r2 = f2.relative_to(ROOT)
                    print(f"    {r1}:{l1} ~ {r2}:{l2}")

    if total == 0:
        print("\n  [OK] No AST issues found.")
        return True
    else:
        print(f"\n  [!] {total} AST issue(s) found — review recommended.")
        return False


def _show_coverage_results(issues: list):
    print(f"\n{'='*60}")
    print("  COVERAGE AUDIT RESULTS")
    print(f"{'='*60}")

    if not issues:
        print("\n  [OK] All files have good coverage.")
        return True

    if issues[0][2].startswith("ERROR"):
        print(f"\n  [ERR] {issues[0][0]}")
        return False

    print(f"\n  [!] {len(issues)} file(s) with low coverage:\n")
    for fname, pct, reason in issues:
        print(f"    {pct:5.1f}%  {fname}")
        print(f"           {reason}")
    print("\n  Action: Add tests for uncovered paths.")
    return False


def _audit_test_quality() -> list[str]:
    """Test rule enforcement — runs in full mode only.

    Each check maps 1:1 to a rule in ai_rules.md §2 or §15.
    No heuristics that can fire on legitimate code.
    """
    import ast

    tests_dir = TESTS
    if not tests_dir.exists():
        return []

    issues: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.violations: list[str] = []

        def visit_Call(self, node: ast.Call) -> None:
            # §15.3: load_config() ban — unambiguous: function name
            if isinstance(node.func, ast.Name) and node.func.id == "load_config":
                self.violations.append("load_config() call (§15.3)")

            # §15 DETERMINISM: time.sleep ban — unambiguous: attribute access
            if (isinstance(node.func, ast.Attribute)
                    and node.func.attr == "sleep"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in ("time", "asyncio")):
                self.violations.append(f"{node.func.value.id}.sleep() (§15 DETERMINISM)")

            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            # §6: inline mock ban — whitelist exact names, no regex
            ALLOWED_MOCKS = frozenset({
                "MockLLM", "MockEmbedder", "Mock", "AsyncMock", "MagicMock",
                "NonCallableMock", "PropertyMock",
            })
            if node.name.endswith("Mock") and node.name not in ALLOWED_MOCKS:
                self.violations.append(f"inline mock class '{node.name}' (§6)")
            self.generic_visit(node)

    for path in tests_dir.rglob("*.py"):
        if path.name in ("conftest.py", "test_config.py"):
            continue

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        visitor = _Visitor()
        visitor.visit(tree)

        for v in visitor.violations:
            rel = path.relative_to(ROOT)
            issues.append(f"  {rel}: {v}")

    return issues


def _show_test_audit_results(issues: list[str]) -> bool:
    print(f"\n{'='*60}")
    print("  TEST QUALITY AUDIT")
    print(f"{'='*60}")

    if not issues:
        print("\n  [OK] No test quality violations.")
        return True

    print(f"\n  [!] {len(issues)} violation(s):\n")
    for issue in issues:
        print(issue)
    print("\n  Rules: §15 ISOLATION, §15 DETERMINISM, §6 Mock adapters.")
    return False


def main() -> int:
    # Always log to file in project root
    log = setup_logging()
    log.__enter__()

    try:
        print("\n  CHECK ALL — Unified project validation")
        print("  " + "=" * 56)
        print("\n  [1]  tests          — pytest only (fast)")
        print("  [2]  tests+coverage — pytest + branch coverage + audit")
        print("  [3]  lint           — ruff + mypy")
        print("  [4]  audit          — AST dead code audit (no tests)")
        print("  [5]  full           — lint → tests → coverage → audit")
        print()

        try:
            choice = input("  Choice [5]: ").strip() or "5"
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return 0

        ok = True

        if choice == "1":
            ok &= _run_cmd([sys.executable, "-m", "pytest", str(TESTS), "-v", "--tb=short"], "TESTS")

        elif choice == "2":
            ok &= _run_cmd([
                sys.executable, "-m", "pytest", str(TESTS),
                "--cov=src/ai_assistant", "--cov-branch",
                "--cov-report=term-missing:skip-covered",
                "-v", "--tb=short",
            ], "TESTS + COVERAGE")
            cov_ok = _show_coverage_results(run_coverage_audit())
            ok &= cov_ok

        elif choice == "3":
            ok &= _run_cmd([sys.executable, "-m", "ruff", "check", "src/ai_assistant"], "RUFF LINT")
            ok &= _run_cmd([sys.executable, "-m", "mypy", "src/ai_assistant"], "MYPY TYPE CHECK")

        elif choice == "4":
            orphaned, unused, methods, consts, dups, cycles = run_ast_audit(SRC)
            ast_ok = _show_ast_results(orphaned, unused, methods, consts, dups, cycles)
            ok &= ast_ok

        elif choice == "5":
            # Full pipeline
            ok &= _run_cmd([sys.executable, "-m", "ruff", "check", "src/ai_assistant"], "RUFF LINT")
            if not ok:
                print("\n  Stopping — fix lint errors first.")
                return 1

            ok &= _run_cmd([sys.executable, "-m", "mypy", "src/ai_assistant"], "MYPY TYPE CHECK")
            if not ok:
                print("\n  Stopping — fix type errors first.")
                return 1

            ok &= _run_cmd([
                sys.executable, "-m", "pytest", str(TESTS),
                "--cov=src/ai_assistant", "--cov-branch",
                "--cov-report=term-missing:skip-covered",
                "-v", "--tb=short",
            ], "TESTS + COVERAGE")
            if not ok:
                print("\n  Stopping — fix test failures first.")
                return 1

            cov_ok = _show_coverage_results(run_coverage_audit())
            ast_ok = _show_ast_results(*run_ast_audit(SRC))
            test_ok = _show_test_audit_results(_audit_test_quality())

            ok &= cov_ok and ast_ok and test_ok

        else:
            print(f"\n  [ERR] Unknown choice: {choice}")
            return 1

        print(f"\n{'='*60}")
        if ok:
            print("  [OK] ALL CHECKS PASSED")
        else:
            print("  [WARN] SOME CHECKS NEED ATTENTION")
        print(f"{'='*60}")

        return 0 if ok else 1

    finally:
        log.__exit__(None, None, None)
        # Print log path to console (bypassing closed log)
        sys.stdout.write(f"\n  Log saved to: {log.log_path}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
