#!/usr/bin/env python3
"""check_all.py — Unified project validation.

Universally checks any Python project with standard tools:
- ruff (lint)
- mypy (types)
- pytest + coverage (tests + branch coverage)
- coverage audit (analyzes .coverage JSON for low coverage)
- AST audit (dead code, duplicates, cycles via ast module)
- i18n audit (cyrillic identifiers and emoji in source)

Usage:
    python scripts/check_all.py         # interactive menu
    python scripts/check_all.py 1       # tests only
    python scripts/check_all.py 5       # full check
"""

import ast
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import types
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import NoReturn

# ── Constants ────────────────────────────────────────────────────────────────
VENV = ".venv"
PY = "Scripts/python.exe" if os.name == "nt" else "bin/python"
_SEP = "─" * 50

SKIP_DIRS: frozenset[str] = frozenset({
    ".venv", "venv", "__pycache__", ".git", "vendor", "ui", "data", "logs", "tmp", "temp", "ops"
})
SKIP_FILES: frozenset[str] = frozenset({"__init__.py"})
ENTRY_POINT_FILES: frozenset[str] = frozenset({"main.py"})
SKIP_NAMES: frozenset[str] = frozenset({"__all__", "__version__"})
SKIP_METHODS: frozenset[str] = frozenset({
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
})

ROUTER_VARIABLE_PREFIXES: tuple[str, ...] = ("router", "admin_router", "api_router")
ABC_BASES: frozenset[str] = frozenset({
    "ABC", "IChunker", "IEmbedder", "ILLM", "IReranker", "IVectorStore",
    "IChatStorage", "ISettingsStorage", "IClosable", "IInitializable",
    "ITool", "IToolRegistry"
})
FRAMEWORK_BASES: frozenset[str] = frozenset({"BaseHTTPMiddleware", "BaseMiddleware", "Middleware"})
FRAMEWORK_CALLBACKS: frozenset[str] = frozenset({"dispatch", "lifespan"})

_CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")
_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
    r"\U00002702-\U000027B0\U000024C2-\U0001F251]+"
)


# ── Auto-activate venv ───────────────────────────────────────────────────────
_venv = Path(__file__).parent.parent / VENV
_venv_py = _venv / PY
if _venv.exists() and _venv_py.exists() and Path(sys.executable).resolve() != _venv_py.resolve():
    if "--venv-relaunched" not in sys.argv:
        os.execl(str(_venv_py), str(_venv_py), *sys.argv, "--venv-relaunched")


# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.resolve()
SRC = ROOT / "src"
TESTS = ROOT / "tests"
COVERAGE_FILE = ROOT / ".coverage"


# ── Helpers ──────────────────────────────────────────────────────────────────
def get_python(root: Path) -> str:
    """Return venv python if available, otherwise system python."""
    venv_py = root / VENV / PY
    return str(venv_py) if venv_py.exists() else sys.executable


def _fmt_duration(seconds: float) -> str:
    """Human-readable duration."""
    if seconds < 1.0:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60.0:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


# ── Logging ──────────────────────────────────────────────────────────────────
class TeeOutput:
    """Redirects stdout/stderr to both console and a log file."""

    def __init__(self, log_path: Path) -> None:
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

    def __enter__(self) -> "TeeOutput":
        sys.stdout = self
        sys.stderr = self
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        sys.stdout = self._stdout
        sys.stderr = self._stderr
        self.close()


def setup_logging() -> TeeOutput:
    """Setup logging to file in data/. Always active."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / f"check_all_{timestamp}.log"
    return TeeOutput(log_path)


# ── AST Audit ────────────────────────────────────────────────────────────────

def collect_py(root: Path) -> list[Path]:
    """Collect all Python files under root, excluding skip dirs/files."""
    return [
        f for f in root.rglob("*.py")
        if f.name not in SKIP_FILES and not any(p in SKIP_DIRS for p in f.parts)
    ]


def parse_file(p: Path) -> ast.AST | None:
    """Parse a Python file; return None on syntax error."""
    try:
        return ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        return None


class _ImportCollector(ast.NodeVisitor):
    def __init__(self, current_module: str = "") -> None:
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


class _ReferenceCollector(ast.NodeVisitor):
    def __init__(self) -> None:
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

    def _collect_decorators(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                self.refs.add(dec.id)
            elif isinstance(dec, ast.Attribute):
                self.refs.add(dec.attr)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._collect_decorators(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._collect_decorators(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._collect_decorators(node)
        self.generic_visit(node)


class _RegistrationCollector(ast.NodeVisitor):
    def __init__(self) -> None:
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

    def _check(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        for dec in node.decorator_list:
            dec_name = self._get_decorator_name(dec)
            if self._is_registration_decorator(dec_name):
                self.registered_names.add(node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._check(node)
        self.generic_visit(node)


class _DefinitionCollector(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.defs: dict[str, tuple[str, int]] = {}
        self.methods: dict[str, dict[str, int]] = {}
        self.classes: dict[str, tuple[int, list[str]]] = {}
        self.exports: set[str] = set()
        self.has_registration_decorator: bool = False
        self._class_stack: list[str] = []

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
        rc = _RegistrationCollector()
        for dec in node.decorator_list:
            dec_name = rc._get_decorator_name(dec)
            if rc._is_registration_decorator(dec_name):
                self.has_registration_decorator = True
                break

    def _add_def(self, name: str, kind: str, line: int) -> None:
        if not name.startswith("_") and name != "main" and name not in SKIP_NAMES:
            self.defs[name] = (kind, line)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_registration_decorator(node)
        if not self._class_stack:
            self._add_def(node.name, "function", node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_registration_decorator(node)
        if not self._class_stack:
            self._add_def(node.name, "async function", node.lineno)
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

    def _collect_assign_targets(self, node: ast.Assign | ast.AnnAssign) -> None:
        targets: Sequence[ast.expr]
        if isinstance(node, ast.Assign):
            targets = node.targets
        else:
            targets = [node.target]

        for target in targets:
            if isinstance(target, ast.Name):
                self._add_def(target.id, "variable", node.lineno)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        self._add_def(elt.id, "variable", node.lineno)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._collect_assign_targets(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._collect_assign_targets(node)


def _build_registry(all_files: list[Path]) -> dict[str, dict[str, object]]:
    registry: dict[str, dict[str, object]] = {}
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

        ic = _ImportCollector(mod)
        ic.visit(tree)

        rc = _ReferenceCollector()
        rc.visit(tree)

        regc = _RegistrationCollector()
        regc.visit(tree)

        dc = _DefinitionCollector(f)
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


def _find_orphaned_files(registry: dict[str, dict[str, object]]) -> list[tuple[Path, str]]:
    all_imports: set[str] = set()
    for info in registry.values():
        all_imports.update(info["imports"])  # type: ignore[arg-type]

    orphaned: list[tuple[Path, str]] = []
    for mod, info in registry.items():
        f: Path = info["file"]  # type: ignore[assignment]
        if f.name in SKIP_FILES or f.name in ENTRY_POINT_FILES or info["has_registration_decorator"] or info["exports"]:  # type: ignore[operator]
            continue
        found = any(
            imp == mod or imp.startswith(f"{mod}.") or imp == f.stem
            for imp in all_imports
        )
        if not found:
            orphaned.append((f, "never imported"))
    return orphaned


def _find_unused_symbols(registry: dict[str, dict[str, object]]) -> list[tuple[Path, str, str, int]]:
    global_refs: set[str] = set()
    for info in registry.values():
        global_refs.update(info["refs"])  # type: ignore[arg-type]

    unused: list[tuple[Path, str, str, int]] = []
    for mod, info in registry.items():
        f: Path = info["file"]  # type: ignore[assignment]
        for name, (kind, line) in info["defs"].items():  # type: ignore[union-attr]
            if name in SKIP_NAMES or name in info["registered_names"] or name in global_refs or name in info["exports"]:  # type: ignore[operator]
                continue
            unused.append((f, name, kind, line))
    return unused


def _is_framework_class(bases: list[str]) -> bool:
    return any(base in FRAMEWORK_BASES for base in bases)


def _is_abc_class(bases: list[str]) -> bool:
    return any(base in ABC_BASES for base in bases)


def _find_unused_methods(registry: dict[str, dict[str, object]]) -> list[tuple[Path, str, str, int]]:
    unused: list[tuple[Path, str, str, int]] = []
    for mod, info in registry.items():
        f: Path = info["file"]  # type: ignore[assignment]
        for cls_name, methods in info["methods"].items():  # type: ignore[union-attr]
            bases = info["classes"].get(cls_name, (0, []))[1]  # type: ignore[union-attr,index]
            if _is_abc_class(bases):
                continue
            is_framework = _is_framework_class(bases)
            for method, line in methods.items():
                if is_framework and method in FRAMEWORK_CALLBACKS:
                    continue
                found = method in info["refs"]  # type: ignore[operator]
                if not found:
                    for other_mod, other_info in registry.items():
                        if other_mod != mod and method in other_info["refs"]:  # type: ignore[operator]
                            found = True
                            break
                if not found:
                    unused.append((f, f"{cls_name}.{method}", "method", line))
    return unused


def _find_dead_constants(registry: dict[str, dict[str, object]]) -> list[tuple[Path, str, int]]:
    dead: list[tuple[Path, str, int]] = []
    for mod, info in registry.items():
        f: Path = info["file"]  # type: ignore[assignment]
        for name, (kind, line) in info["defs"].items():  # type: ignore[union-attr]
            if kind == "variable" and name.isupper() and name not in info["refs"] and name not in info["exports"]:  # type: ignore[operator]
                found = any(name in other["refs"] for other in registry.values())  # type: ignore[operator]
                if not found:
                    dead.append((f, name, line))
    return dead


def _find_duplicate_blocks(registry: dict[str, dict[str, object]], min_lines: int = 5) -> list[tuple[Path, Path, int, int]]:
    if not hasattr(ast, "unparse"):
        return []

    blocks: dict[str, list[tuple[Path, int]]] = {}
    for mod, info in registry.items():
        f: Path = info["file"]  # type: ignore[assignment]
        tree: ast.AST | None = info.get("tree")  # type: ignore[assignment]
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

    duplicates: list[tuple[Path, Path, int, int]] = []
    seen: set[tuple[str, ...]] = set()
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


def _normalize_cycle(cycle_nodes: list[str]) -> tuple[str, ...]:
    if not cycle_nodes:
        return tuple()
    nodes = cycle_nodes[:-1] if cycle_nodes[0] == cycle_nodes[-1] else list(cycle_nodes)
    if not nodes:
        return tuple()
    n = len(nodes)
    return min(tuple(nodes[i:] + nodes[:i]) for i in range(n))


def _check_cycles(registry: dict[str, dict[str, object]]) -> list[str]:
    cycles: list[str] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def dfs(node: str, path: list[str]) -> None:
        for imp in registry[node]["imports"]:  # type: ignore[operator]
            if imp not in registry:
                continue
            if imp in path:
                idx = path.index(imp)
                cycle = path[idx:] + [imp]
                key = _normalize_cycle(cycle)
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
    registry = _build_registry(all_src)
    return (
        _find_orphaned_files(registry),
        _find_unused_symbols(registry),
        _find_unused_methods(registry),
        _find_dead_constants(registry),
        _find_duplicate_blocks(registry, min_lines=5),
        _check_cycles(registry),
    )


# ── Coverage Audit ───────────────────────────────────────────────────────────

def run_coverage_audit() -> list[tuple[str, float, str]]:
    """Analyze .coverage file and return low-coverage files."""
    if not COVERAGE_FILE.exists():
        return [("No .coverage file found — run tests first", 0.0, "ERROR")]

    json_path = ROOT / "coverage_audit_temp.json"
    try:
        result = subprocess.run(
            [get_python(ROOT), "-m", "coverage", "json", "-o", str(json_path), "--pretty-print"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.returncode != 0 or not json_path.exists():
            return [("Failed to generate coverage JSON", 0.0, f"ERROR: {result.stderr[:200]}")]

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return [("Exception during coverage audit", 0.0, f"ERROR: {exc}")]
    finally:
        json_path.unlink(missing_ok=True)

    issues: list[tuple[str, float, str]] = []
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


# ── Test Quality Audit ───────────────────────────────────────────────────────

def _audit_test_quality() -> list[str]:
    """Test rule enforcement — runs in full mode only.

    Each check maps 1:1 to a rule in ai_rules.md §2 or §15.
    Sleep calls annotated with '# noqa: SLEEP' are skipped.
    """
    if not TESTS.exists():
        return []

    ALLOWED_MOCKS: frozenset[str] = frozenset({
        "MockLLM", "MockEmbedder", "Mock", "AsyncMock", "MagicMock",
        "NonCallableMock", "PropertyMock",
    })

    issues: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def __init__(self, source_lines: list[str]) -> None:
            self.violations: list[str] = []
            self._lines = source_lines

        def _has_noqa(self, lineno: int) -> bool:
            if 1 <= lineno <= len(self._lines):
                return "# noqa: SLEEP" in self._lines[lineno - 1]
            return False

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "load_config":
                self.violations.append("load_config() call (§15.3)")
                self.generic_visit(node)
                return

            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "sleep"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in ("time", "asyncio")
            ):
                self.generic_visit(node)
                return

            if self._has_noqa(node.lineno):
                self.generic_visit(node)
                return

            self.violations.append(f"{node.func.value.id}.sleep() (§15 DETERMINISM)")
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if node.name.endswith("Mock") and node.name not in ALLOWED_MOCKS:
                self.violations.append(f"inline mock class '{node.name}' (§6)")
            self.generic_visit(node)

    for path in TESTS.rglob("*.py"):
        if path.name in ("conftest.py", "test_config.py"):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            tree = ast.parse(source)
        except SyntaxError:
            continue

        visitor = _Visitor(lines)
        visitor.visit(tree)

        for v in visitor.violations:
            rel = path.relative_to(ROOT)
            issues.append(f"  {rel}: {v}")

    return issues


# ── I18N / Non-ASCII Audit ───────────────────────────────────────────────────

def _audit_non_ascii(src_dir: Path) -> list[tuple[Path, int, str, str]]:
    """Find cyrillic identifiers and emoji in source code."""
    issues: list[tuple[Path, int, str, str]] = []
    for f in collect_py(src_dir):
        source = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            name: str | None = None
            lineno: int = getattr(node, "lineno", 0)
            kind = "identifier"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = node.name
                kind = "definition"
            elif isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.arg):
                name = node.arg
                kind = "argument"
            elif isinstance(node, ast.keyword):
                name = node.arg
                kind = "keyword"

            if name:
                if _CYRILLIC_RE.search(name):
                    issues.append((f, lineno, "cyrillic-id", f"Cyrillic {kind}: {name}"))
                if _EMOJI_RE.search(name):
                    issues.append((f, lineno, "emoji-id", f"Emoji {kind}: {name}"))

        for lineno, line in enumerate(source.splitlines(), 1):
            if "#" in line:
                comment = line.split("#", 1)[1]
                if _EMOJI_RE.search(comment):
                    emojis = _EMOJI_RE.findall(comment)
                    issues.append((f, lineno, "emoji-comment", f"Emoji in comment: {''.join(emojis)}"))

    return issues


# ── UI ───────────────────────────────────────────────────────────────────────

def _print_menu() -> None:
    print()
    print(_SEP)
    print(f"   CHECK ALL              {time.strftime('%H:%M:%S')}")
    print(_SEP)
    print("  [1]  tests          — pytest only (fast)")
    print("  [2]  tests+coverage — pytest + branch coverage + audit")
    print("  [3]  lint           — ruff + mypy")
    print("  [4]  audit          — AST dead code audit (no tests)")
    print("  [5]  full           — lint → tests → coverage → audit → i18n")
    print("  [6]  i18n           — non-ASCII identifier & emoji audit")
    print(_SEP)
    print()


def _run_cmd(cmd: list[str], desc: str) -> bool:
    print()
    print(f"  {desc}")
    print()

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTEST_CURRENT_TEST"] = ""
    env["TERM"] = "dumb"
    env["PY_COLORS"] = "0"
    env["CI"] = "true"

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
        bufsize=1,
    )

    if process.stdout:
        for line in iter(process.stdout.readline, ""):
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


def _show_ast_results(
    orphaned: list[tuple[Path, str]],
    unused: list[tuple[Path, str, str, int]],
    methods: list[tuple[Path, str, str, int]],
    consts: list[tuple[Path, str, int]],
    dups: list[tuple[Path, Path, int, int]],
    cycles: list[str],
) -> bool:
    print()
    print("  AST AUDIT RESULTS")
    print()

    total = 0

    if orphaned:
        total += len(orphaned)
        print(f"\n  Orphaned files  ({len(orphaned)}):")
        for f, reason in orphaned:
            print(f"    {f.relative_to(ROOT)}  -- {reason}")

    if unused:
        total += len(unused)
        print(f"\n  Unused symbols  ({len(unused)}):")
        for f, name, kind, line in unused:
            print(f"    {f.relative_to(ROOT)}:{line}  -- {kind} {name}")

    if methods:
        total += len(methods)
        print(f"\n  Unused methods  ({len(methods)}):")
        for f, name, kind, line in methods:
            print(f"    {f.relative_to(ROOT)}:{line}  -- {kind} {name}")

    if consts:
        total += len(consts)
        print(f"\n  Dead constants  ({len(consts)}):")
        for f, name, line in consts:
            print(f"    {f.relative_to(ROOT)}:{line}  -- {name}")

    if dups:
        total += len(dups)
        print(f"\n  Duplicate blocks  ({len(dups)}):")
        for f1, f2, l1, l2 in dups:
            print(f"    {f1.relative_to(ROOT)}:{l1} ~ {f2.relative_to(ROOT)}:{l2}")

    if cycles:
        total += len(cycles)
        print(f"\n  Circular imports  ({len(cycles)}):")
        for cycle in cycles:
            print(f"    {cycle}")

    if total == 0:
        print("\n  [OK] No AST issues found.")
        return True
    else:
        print(f"\n  [!] {total} AST issue(s) found — review recommended.")
        return False


def _show_coverage_results(issues: list[tuple[str, float, str]]) -> bool:
    print()
    print("  COVERAGE AUDIT RESULTS")
    print()

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


def _show_test_audit_results(issues: list[str]) -> bool:
    print()
    print("  TEST QUALITY AUDIT")
    print()

    if not issues:
        print("\n  [OK] No test quality violations.")
        return True

    print(f"\n  [!] {len(issues)} violation(s):\n")
    for issue in issues:
        print(issue)
    print("\n  Rules: §15 ISOLATION, §15 DETERMINISM, §6 Mock adapters.")
    return False


def _show_non_ascii_results(issues: list[tuple[Path, int, str, str]]) -> bool:
    print()
    print("  I18N / NON-ASCII AUDIT")
    print()

    if not issues:
        print("\n  [OK] No non-ASCII identifiers or emoji found.")
        return True

    cyrillic = [i for i in issues if i[2] == "cyrillic-id"]
    emoji_id = [i for i in issues if i[2] == "emoji-id"]
    emoji_comment = [i for i in issues if i[2] == "emoji-comment"]

    if cyrillic:
        print(f"\n  [!] Cyrillic identifiers  ({len(cyrillic)}):")
        for f, line, _, msg in cyrillic:
            print(f"    {f.relative_to(ROOT)}:{line}  {msg}")

    if emoji_id:
        print(f"\n  [!] Emoji identifiers  ({len(emoji_id)}):")
        for f, line, _, msg in emoji_id:
            print(f"    {f.relative_to(ROOT)}:{line}  {msg}")

    if emoji_comment:
        print(f"\n  [!] Emoji in comments  ({len(emoji_comment)}):")
        for f, line, _, msg in emoji_comment:
            print(f"    {f.relative_to(ROOT)}:{line}  {msg}")

    print(f"\n  [!] {len(issues)} issue(s) found — review recommended.")
    return False


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    log = setup_logging()
    log.__enter__()

    def _on_sigint(_signum: int, _frame: types.FrameType | None) -> NoReturn:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)

    try:
        _print_menu()

        try:
            choice = input("  Choice [5]: ").strip() or "5"
        except EOFError:
            print("\n  ! Input stream closed. Exiting.")
            return 1
        except KeyboardInterrupt:
            print("\n  ! Interrupted by user. Exiting.")
            return 0

        ok = True
        py = get_python(ROOT)

        if choice in ("0", "exit", "q", "quit"):
            print("\n  Bye.\n")
            return 0

        if choice == "1":
            ok &= _run_cmd([py, "-m", "pytest", str(TESTS), "-v", "--tb=short"], "TESTS")

        elif choice == "2":
            ok &= _run_cmd(
                [
                    py, "-m", "pytest", str(TESTS),
                    "--cov=src/ai_assistant", "--cov-branch",
                    "--cov-report=term-missing:skip-covered",
                    "-v", "--tb=short",
                ],
                "TESTS + COVERAGE",
            )
            ok &= _show_coverage_results(run_coverage_audit())

        elif choice == "3":
            ok &= _run_cmd([py, "-m", "ruff", "check", "src/ai_assistant"], "RUFF LINT")
            ok &= _run_cmd([py, "-m", "mypy", "src/ai_assistant"], "MYPY TYPE CHECK")

        elif choice == "4":
            ast_ok = _show_ast_results(*run_ast_audit(SRC))
            ok &= ast_ok

        elif choice == "5":
            ok &= _run_cmd([py, "-m", "ruff", "check", "src/ai_assistant"], "RUFF LINT")
            if not ok:
                print("\n  Stopping — fix lint errors first.")
                return 1

            ok &= _run_cmd([py, "-m", "mypy", "src/ai_assistant"], "MYPY TYPE CHECK")
            if not ok:
                print("\n  Stopping — fix type errors first.")
                return 1

            ok &= _run_cmd(
                [
                    py, "-m", "pytest", str(TESTS),
                    "--cov=src/ai_assistant", "--cov-branch",
                    "--cov-report=term-missing:skip-covered",
                    "-v", "--tb=short",
                ],
                "TESTS + COVERAGE",
            )
            if not ok:
                print("\n  Stopping — fix test failures first.")
                return 1

            ok &= _show_coverage_results(run_coverage_audit())
            ok &= _show_ast_results(*run_ast_audit(SRC))
            ok &= _show_test_audit_results(_audit_test_quality())
            ok &= _show_non_ascii_results(_audit_non_ascii(SRC))

        elif choice == "6":
            ok &= _show_non_ascii_results(_audit_non_ascii(SRC))

        else:
            print(f"\n  [ERR] Unknown choice: {choice}")
            return 1

        print()
        if ok:
            print("  [OK] ALL CHECKS PASSED")
        else:
            print("  [WARN] SOME CHECKS NEED ATTENTION")
        print()

        return 0 if ok else 1

    except EOFError:
        print("\n  ! Input stream closed. Exiting.")
        return 1
    except KeyboardInterrupt:
        print("\n  ! Interrupted by user. Exiting.")
        return 0
    except Exception as e:
        print(f"\n  ! Unexpected error: {e}")
        try:
            input("  Press Enter to continue...")
        except EOFError:
            return 1
        return 1
    finally:
        log.__exit__(None, None, None)
        sys.stdout.write(f"\n  Log saved to: {log.log_path}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
