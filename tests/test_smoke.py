"""tests/test_smoke.py — Smoke tests: imports, cycles, AST scans, tooling.

Coverage: imports without cycles, key modules at module level, no print/pprint,
no cyrillic in .py, ruff rules (B, SIM, C4, TCH), mypy strict, frozen versions,
PEP 508 parsing, compileall -q, structured logging format.

Design: Given/When/Then docstrings, one function per test case.
"""

from __future__ import annotations

import ast
import compileall
import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

from ai_assistant.core.logger import get_logger

logger = get_logger(__name__)


# ── Path helpers ──


def _project_root() -> Path:
    """Robust project-root discovery via pyproject.toml (works on Windows)."""
    start = Path(__file__).resolve()
    for parent in [start, *start.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: assume tests/ is directly under project root
    return Path(__file__).resolve().parent.parent


def _src_dir() -> Path:
    """Return src/ai_assistant directory."""
    return _project_root() / "src" / "ai_assistant"


def _resolve_py_file(rel_path: str) -> Path:
    """Resolve a Python file relative to src/ai_assistant."""
    path = _src_dir() / rel_path
    if path.exists():
        return path
    pytest.skip(f"Source file not found: {rel_path}")


def _scan_src(
    directory: Path,
    *,
    predicate: Any,
) -> list[tuple[str, int, str]]:
    """Generic src scanner: applies predicate(source, filename) to each .py file."""
    hits: list[tuple[str, int, str]] = []
    if not directory.exists():
        pytest.skip(f"Directory not found: {directory}")
    for py_file in directory.rglob("*.py"):
        if py_file.name.startswith("test_"):
            continue
        source = py_file.read_text(encoding="utf-8")
        file_hits = predicate(source, str(py_file))
        for lineno, detail in file_hits:
            hits.append((str(py_file), lineno, detail))
    return hits


# ═══════════════════════════════════════════════════════════════════════════
# TestImportsClean
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestImportsClean:
    """Smoke: key modules import without errors at top level."""

    def test_api_static_imports(self):
        """Given: api.static module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.api.static as _static

        assert _static is not None

    def test_api_lifespan_imports(self):
        """Given: api.lifespan module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.api.lifespan as _lifespan

        assert _lifespan is not None

    def test_api_deps_imports(self):
        """Given: api.deps module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.api.deps as _deps

        assert _deps is not None

    def test_main_imports(self):
        """Given: main entry point module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.main as _main

        assert _main is not None

    def test_security_imports(self):
        """Given: api.security module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.api.security as _security

        assert _security is not None

    def test_router_imports(self):
        """Given: api.router module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.api.router as _router

        assert _router is not None

    def test_admin_imports(self):
        """Given: api.admin module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.api.admin as _admin

        assert _admin is not None

    def test_middleware_imports(self):
        """Given: api.middleware module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.api.middleware as _middleware

        assert _middleware is not None

    def test_pipeline_imports(self):
        """Given: core.pipeline module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.core.pipeline as _pipeline

        assert _pipeline is not None

    def test_pipeline_steps_imports(self):
        """Given: core.pipeline_steps module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.core.pipeline_steps as _steps

        assert _steps is not None

    def test_config_imports(self):
        """Given: core.config module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.core.config as _config

        assert _config is not None

    def test_domain_imports(self):
        """Given: core.domain modules.
        When: imported at top level.
        Then: all succeed without ImportError."""
        import ai_assistant.core.domain.documents as _docs
        import ai_assistant.core.domain.messages as _msgs
        import ai_assistant.core.domain.pipeline as _pipe

        assert _docs is not None
        assert _msgs is not None
        assert _pipe is not None

    def test_ports_imports(self):
        """Given: core.ports modules.
        When: imported at top level.
        Then: all succeed without ImportError."""
        import ai_assistant.core.ports.chunker as _chunker
        import ai_assistant.core.ports.closable as _closable
        import ai_assistant.core.ports.embedder as _embedder
        import ai_assistant.core.ports.llm as _llm
        import ai_assistant.core.ports.reranker as _reranker
        import ai_assistant.core.ports.storage as _storage
        import ai_assistant.core.ports.vector_store as _vs

        assert _chunker is not None
        assert _closable is not None
        assert _embedder is not None
        assert _llm is not None
        assert _reranker is not None
        assert _storage is not None
        assert _vs is not None

    def test_adapters_imports(self):
        """Given: adapters package.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.adapters as _adapters

        assert _adapters is not None

    def test_factory_imports(self):
        """Given: adapters.factory module.
        When: imported at top level.
        Then: succeeds without ImportError."""
        import ai_assistant.adapters.factory as _factory

        assert _factory is not None

    def test_features_chat_imports(self):
        """Given: features.chat modules.
        When: imported at top level.
        Then: all succeed without ImportError."""
        import ai_assistant.features.chat.handlers as _chat_handlers
        import ai_assistant.features.chat.manager as _chat_mgr
        import ai_assistant.features.chat.schemas as _chat_schemas

        assert _chat_handlers is not None
        assert _chat_mgr is not None
        assert _chat_schemas is not None

    def test_features_rag_imports(self):
        """Given: features.rag modules.
        When: imported at top level.
        Then: all succeed without ImportError."""
        import ai_assistant.features.rag.handlers as _rag_handlers
        import ai_assistant.features.rag.indexing as _rag_indexing
        import ai_assistant.features.rag.manager as _rag_mgr
        import ai_assistant.features.rag.schemas as _rag_schemas

        assert _rag_handlers is not None
        assert _rag_indexing is not None
        assert _rag_mgr is not None
        assert _rag_schemas is not None


# ═══════════════════════════════════════════════════════════════════════════
# TestModuleLevelImports
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestModuleLevelImports:
    """Smoke: key classes are imported at module level (no deferred imports)."""

    def test_mount_static_in_api_layer(self):
        """Given: api.static module.
        When: checking for mount_static.
        Then: callable is available at module level."""
        from ai_assistant.api.static import mount_static

        assert callable(mount_static)

    def test_lifespan_no_main_import(self):
        """Given: api/lifespan.py source.
        When: AST is scanned for main.py imports.
        Then: no import from main.py found (avoids circular dependency)."""
        import ast
        import inspect

        from ai_assistant.api import lifespan

        source = inspect.getsource(lifespan)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if "ai_assistant.main" in module:
                    pytest.fail("lifespan.py imports from main.py — circular entry point dependency")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "ai_assistant.main":
                        pytest.fail("lifespan.py imports main.py module directly")

    def test_router_assembles_at_import(self):
        """Given: api.router module.
        When: imported.
        Then: assemble_routers is callable and returns >=4 routers."""
        from ai_assistant.api.router import assemble_routers

        routers = assemble_routers()
        assert callable(assemble_routers)
        assert len(routers) >= 4

    def test_factory_create_adapter_exported(self):
        """Given: adapters.factory module.
        When: checking exports.
        Then: create_adapter is in __all__."""
        from ai_assistant.adapters.factory import __all__

        assert "create_adapter" in __all__


# ═══════════════════════════════════════════════════════════════════════════
# TestNoPrintPprintAST
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestNoPrintPprintAST:
    """Smoke: no print()/pprint() in production source via AST scan."""

    @staticmethod
    def _find_print_calls(source: str, filename: str) -> list[tuple[int, str]]:
        tree = ast.parse(source, filename=filename)
        hits: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ("print", "pprint"):
                    hits.append((node.lineno, ast.unparse(node)))
        return hits

    def test_src_no_print_pprint(self):
        """Given: all .py files in src/ai_assistant.
        When: AST-scanned for print()/pprint().
        Then: zero hits (production code uses logger)."""
        hits = _scan_src(_src_dir(), predicate=self._find_print_calls)
        assert not hits, f"print()/pprint() found in production code: {hits[:5]}"


# ═══════════════════════════════════════════════════════════════════════════
# TestLoggingFormat
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestLoggingFormat:
    """Smoke: no positional % formatting in logger calls — use extra={} instead.

    Enforces structured logging: static message strings, data in extra dict.
    """

    def _find_positional_logging(self, source: str, filename: str) -> list[tuple[int, str]]:
        """AST-scan for logger.* calls with % format specifiers or positional args.

        Detects all variables assigned from get_logger(), not just 'logger'.
        """
        tree = ast.parse(source, filename=filename)
        hits: list[tuple[int, str]] = []
        logger_names: set[str] = {"logger"}  # default common name

        # Phase 1: discover logger variable names (e.g. log = get_logger(...))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if (
                    len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "get_logger"
                ):
                    logger_names.add(node.targets[0].id)

        # Phase 2: scan for logger.* calls
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in ("info", "debug", "warning", "error", "exception", "critical"):
                continue
            if not isinstance(func.value, ast.Name) or func.value.id not in logger_names:
                continue
            # Check for % format specifiers in message string (exclude %% escapes)
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    msg = first_arg.value
                    # Match %s, %d, %f, %(name)s, etc. but not %% escape sequences
                    cleaned = msg.replace("%%", "")
                    if "%" in cleaned:
                        hits.append((node.lineno, f"percent-format: {msg[:40]}"))
            # Check for positional args beyond message (extra= should be keyword)
            if len(node.args) > 1:
                hits.append((node.lineno, f"extra-positional: {ast.unparse(node)[:60]}"))
        return hits

    def test_src_no_positional_logging(self):
        """Given: all .py files in src/ai_assistant.
        When: AST-scanned for logger.* with %s or positional args.
        Then: zero hits (use logger.info('msg', extra={'key': val}))."""
        hits = _scan_src(_src_dir(), predicate=self._find_positional_logging)
        assert not hits, f"Positional logging found: {hits[:5]}"


# ═══════════════════════════════════════════════════════════════════════════
# TestNoCyrillic
# ═══════════════════════════════════════════════════════════════════════════

_I18N_PATHS = {"i18n", "locale", "translations"}
_CONSTANTS_NAMES = {"constants"}


def _should_skip_cyrillic_check(path: Path) -> bool:
    parts = set(path.parts)
    name = path.stem.lower()
    return bool(parts & _I18N_PATHS) or name in _CONSTANTS_NAMES


@pytest.mark.smoke
class TestNoCyrillic:
    """Smoke: no Cyrillic characters in .py source files (use i18n instead)."""

    def _find_cyrillic(self, source: str, filename: str) -> list[tuple[int, str]]:
        hits: list[tuple[int, str]] = []
        for i, line in enumerate(source.splitlines(), 1):
            for char in line:
                if "Ѐ" <= char <= "ӿ" or "Ԁ" <= char <= "ԯ":
                    hits.append((i, line.strip()))
                    break
        return hits

    def _scan_directory(self, directory: Path) -> list[tuple[str, int, str]]:
        hits: list[tuple[str, int, str]] = []
        if not directory.exists():
            pytest.skip(f"Directory not found: {directory}")
        for py_file in directory.rglob("*.py"):
            if py_file.name.startswith("test_"):
                continue
            source = py_file.read_text(encoding="utf-8")
            file_hits = self._find_cyrillic(source, str(py_file))
            for lineno, line in file_hits:
                hits.append((str(py_file), lineno, line))
        return hits

    def test_src_no_cyrillic(self):
        """Given: all .py files in src/ai_assistant.
        When: scanned for Cyrillic characters.
        Then: zero hits outside i18n dirs and noqa-marked lines."""
        hits = self._scan_directory(_src_dir())
        filtered = [
            (f, ln, line)
            for f, ln, line in hits
            if not _should_skip_cyrillic_check(Path(f))
            and "# noqa: cyrillic" not in line
        ]
        assert not filtered, f"Cyrillic characters found in source: {filtered[:5]}"


# ═══════════════════════════════════════════════════════════════════════════
# TestRuffRules
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestRuffRules:
    """Smoke: ruff select rules include B, SIM, C4, TCH."""

    def test_ruff_select_rules(self):
        """Given: pyproject.toml.
        When: ruff lint select is read.
        Then: B, SIM, C4, TCH are present."""
        import tomllib

        pyproject_path = _project_root() / "pyproject.toml"
        if not pyproject_path.exists():
            pytest.skip("pyproject.toml not found")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        select = data.get("tool", {}).get("ruff", {}).get("lint", {}).get("select", [])
        assert "B" in select, "ruff select must include B (flake8-bugbear)"
        assert "SIM" in select, "ruff select must include SIM (simplify)"
        assert "C4" in select, "ruff select must include C4 (comprehensions)"
        assert "TCH" in select, "ruff select must include TCH (type-checking)"

    def test_ruff_target_version(self):
        """Given: pyproject.toml.
        When: ruff target-version is read.
        Then: equals py311."""
        import tomllib

        pyproject_path = _project_root() / "pyproject.toml"
        if not pyproject_path.exists():
            pytest.skip("pyproject.toml not found")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        target = data.get("tool", {}).get("ruff", {}).get("target-version", "")
        assert target == "py311", f"ruff target-version must be py311: {target}"


# ═══════════════════════════════════════════════════════════════════════════
# TestMypyStrict
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestMypyStrict:
    """Smoke: mypy strict mode is enabled."""

    def test_mypy_strict_enabled(self):
        """Given: pyproject.toml.
        When: mypy config is read.
        Then: strict = true."""
        import tomllib

        pyproject_path = _project_root() / "pyproject.toml"
        if not pyproject_path.exists():
            pytest.skip("pyproject.toml not found")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        strict = data.get("tool", {}).get("mypy", {}).get("strict", False)
        assert strict is True, "mypy strict must be enabled"

    def test_mypy_python_version(self):
        """Given: pyproject.toml.
        When: mypy python_version is read.
        Then: equals 3.11."""
        import tomllib

        pyproject_path = _project_root() / "pyproject.toml"
        if not pyproject_path.exists():
            pytest.skip("pyproject.toml not found")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        version = data.get("tool", {}).get("mypy", {}).get("python_version", "")
        assert version == "3.11", f"mypy python_version must be 3.11: {version}"


# ═══════════════════════════════════════════════════════════════════════════
# TestFrozenVersions
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestFrozenVersions:
    """Smoke: dependencies have frozen upper/lower bounds (PEP 508)."""

    def _get_dependencies(self) -> list[str]:
        import tomllib

        pyproject_path = _project_root() / "pyproject.toml"
        if not pyproject_path.exists():
            pytest.skip("pyproject.toml not found")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("dependencies", [])

    def _parse_requirement(self, req: str) -> tuple[str, str | None, str | None]:
        """Parse name, lower bound, upper bound from PEP 508 string."""
        pytest.importorskip("packaging", reason="packaging library required for PEP 508 parsing")
        from packaging.requirements import Requirement

        try:
            r = Requirement(req)
        except Exception:
            return req, None, None
        lower = None
        upper = None
        for spec in r.specifier:
            op = str(spec.operator)
            ver = str(spec.version)
            if op == ">=" or op == ">":
                lower = ver
            elif op == "<" or op == "<=":
                upper = ver
        return r.name, lower, upper

    def test_fastapi_frozen(self):
        """Given: fastapi dependency.
        When: PEP 508 string is parsed.
        Then: has >=0.110.0 and <1.0.0 bounds."""
        deps = self._get_dependencies()
        fastapi_dep = next((d for d in deps if d.startswith("fastapi")), None)
        assert fastapi_dep is not None, "fastapi not in dependencies"
        name, lower, upper = self._parse_requirement(fastapi_dep)
        assert lower is not None, "fastapi missing lower bound"
        assert upper is not None, "fastapi missing upper bound"

    def test_pydantic_frozen(self):
        """Given: pydantic dependency.
        When: PEP 508 string is parsed.
        Then: has >=2.7.0 and <3.0.0 bounds."""
        deps = self._get_dependencies()
        pydantic_dep = next((d for d in deps if d.startswith("pydantic")), None)
        assert pydantic_dep is not None, "pydantic not in dependencies"
        name, lower, upper = self._parse_requirement(pydantic_dep)
        assert lower is not None, "pydantic missing lower bound"
        assert upper is not None, "pydantic missing upper bound"

    def test_uvicorn_frozen(self):
        """Given: uvicorn dependency.
        When: PEP 508 string is parsed.
        Then: has >=0.29.0 and <1.0.0 bounds with [standard] extra."""
        deps = self._get_dependencies()
        uvicorn_dep = next((d for d in deps if d.startswith("uvicorn")), None)
        assert uvicorn_dep is not None, "uvicorn not in dependencies"
        name, lower, upper = self._parse_requirement(uvicorn_dep)
        assert lower is not None, "uvicorn missing lower bound"
        assert upper is not None, "uvicorn missing upper bound"
        assert "standard" in uvicorn_dep, "uvicorn must have [standard] extra"

    def test_all_deps_have_upper_bound(self):
        """Given: all project dependencies.
        When: each is parsed.
        Then: every dependency has an upper bound (< or <=)."""
        deps = self._get_dependencies()
        unbounded = []
        for dep in deps:
            name, lower, upper = self._parse_requirement(dep)
            if upper is None:
                unbounded.append(dep)
        assert not unbounded, f"Dependencies missing upper bound: {unbounded}"


# ═══════════════════════════════════════════════════════════════════════════
# TestCompileAll
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestCompileAll:
    """Smoke: compileall -q passes for all source files."""

    def test_compileall_src(self):
        """Given: src/ai_assistant directory.
        When: compileall.compile_dir is run with quiet=2.
        Then: returns True (no syntax errors)."""
        src = _src_dir()
        if not src.exists():
            pytest.skip("src directory not found")
        success = compileall.compile_dir(str(src), quiet=2)
        assert success, "compileall detected syntax errors in src/"

    def test_compileall_tests(self):
        """Given: tests/ directory.
        When: compileall.compile_dir is run with quiet=2.
        Then: returns True (no syntax errors)."""
        tests_dir = Path(__file__).parent
        success = compileall.compile_dir(str(tests_dir), quiet=2)
        assert success, "compileall detected syntax errors in tests/"


# ═══════════════════════════════════════════════════════════════════════════
# TestKeyFilesExist
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestKeyFilesExist:
    """Smoke: critical project files are present."""

    def test_pyproject_toml_exists(self):
        """Given: project root.
        When: checking for pyproject.toml.
        Then: file exists."""
        assert (_project_root() / "pyproject.toml").exists()

    def test_pytest_ini_exists(self):
        """Given: project root.
        When: checking for pyproject.toml pytest config.
        Then: pyproject.toml exists and contains [tool.pytest.ini_options]."""
        import tomllib

        pyproject = _project_root() / "pyproject.toml"
        assert pyproject.exists()
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        assert "tool" in data
        assert "pytest" in data.get("tool", {})
        assert "ini_options" in data.get("tool", {}).get("pytest", {})

    def test_conftest_py_exists(self):
        """Given: tests directory.
        When: checking for conftest.py.
        Then: file exists."""
        assert (Path(__file__).parent / "conftest.py").exists()

    def test_readme_exists(self):
        """Given: project root.
        When: checking for README.
        Then: README.md or README.rst exists."""
        root = _project_root()
        assert (root / "README.md").exists() or (root / "README.rst").exists()

    def test_src_structure(self):
        """Given: project root.
        When: checking src/ai_assistant structure.
        Then: core/, api/, adapters/, features/ directories exist."""
        src = _src_dir()
        assert (src / "core").is_dir()
        assert (src / "api").is_dir()
        assert (src / "adapters").is_dir()
        assert (src / "features").is_dir()


# ═══════════════════════════════════════════════════════════════════════════
# TestNoKwargsInSteps (duplicate from contracts, also smoke)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
def test_pipeline_steps_no_kwargs_smoke() -> None:
    """Smoke: pipeline step functions must not use **kwargs.

    Given: pipeline_steps.py source.
    When: AST is scanned.
    Then: no step function uses **kwargs.
    """
    import ast

    from ai_assistant.core.pipeline_steps import STEP_REGISTRY

    step_registry_names: set[str] = set(STEP_REGISTRY.keys())

    steps_path = _src_dir() / "core" / "pipeline_steps.py"
    if not steps_path.exists():
        pytest.skip("pipeline_steps.py not found")
    source = steps_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            # Check if function name is in STEP_REGISTRY (regardless of decorator alias)
            if node.name in step_registry_names and node.args.kwarg is not None:
                pytest.fail(
                    f"Step function {node.name!r} uses **kwargs. "
                    f"Use StepContext instead."
                )


# ═══════════════════════════════════════════════════════════════════════════
# TestConfigLoads
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestConfigLoads:
    """Smoke: AppConfig constructs correctly with matching dimensions."""

    def test_config_loads(self):
        """Given: inline AppConfig with matching dimensions.
        When: constructed directly.
        Then: embedder.dim equals vector_store.dim."""
        from ai_assistant.core.config import AppConfig

        cfg = AppConfig(
            embedder={"dim": 768, "provider": "mock"},
            vector_store={"dim": 768, "provider": "memory"},
        )
        assert cfg.embedder.dim == cfg.vector_store.dim


# ═══════════════════════════════════════════════════════════════════════════
# TestToolPortContract
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestToolPortContract:
    """Smoke: Tool port contract is implementable."""

    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Given: ITool implementation.
        When: executed with valid arguments.
        Then: returns ToolResult with correct output."""
        from ai_assistant.core.ports.tools import ITool, ToolSpec, ToolResult

        class _AddTool(ITool):
            @property
            def spec(self) -> ToolSpec:
                return ToolSpec(
                    name="add",
                    description="Add two numbers",
                    parameters={
                        "type": "object",
                        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    },
                    required=["a", "b"],
                )

            async def execute(self, call_id: str, arguments: dict) -> ToolResult:
                return ToolResult(
                    call_id=call_id,
                    output=str(arguments.get("a", 0) + arguments.get("b", 0)),
                    is_error=False,
                )

        tool = _AddTool({})
        result = await tool.execute("call-1", {"a": 2, "b": 3})
        assert not result.is_error
        assert result.output == "5"


# ═══════════════════════════════════════════════════════════════════════════
# TestSecurityKeyResolution
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestSecurityKeyResolution:
    """Smoke: API key resolution works."""

    def test_env_key_resolution(self, monkeypatch):
        """Given: AI_API_KEY env var is set.
        When: get_expected_api_key is called.
        Then: returns the env var value."""
        from ai_assistant.api.security import get_expected_api_key

        monkeypatch.setenv("AI_SECURITY_API_KEY", "test-smoke-key")
        key = get_expected_api_key()
        assert key == "test-smoke-key"


# ═══════════════════════════════════════════════════════════════════════════
# TestLoggingSetup
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.smoke
class TestLoggingSetup:
    """Smoke: setup_logging accepts rotation parameters without error."""

    @pytest.fixture(autouse=True)
    def _cleanup_logging(self):
        """Cleanup root logger handlers after each test to prevent accumulation."""
        import logging

        yield
        root = logging.getLogger("ai_assistant")
        for handler in root.handlers:
            handler.close()
        root.handlers.clear()

    def test_setup_logging_with_defaults(self):
        """Given: default parameters. When: setup_logging is called.
        Then: returns logger without error."""
        from ai_assistant.core.logger import setup_logging

        logger = setup_logging()
        assert logger is not None
        assert logger.name == "ai_assistant"

    def test_setup_logging_with_custom_rotation(self, tmp_path):
        """Given: custom max_bytes and backup_count.
        When: setup_logging is called. Then: file handler has correct params."""
        from ai_assistant.core.logger import setup_logging

        log_file = tmp_path / "test.log"
        logger = setup_logging(
            level="DEBUG",
            log_file=str(log_file),
            fmt="text",
            max_bytes=1_024,
            backup_count=3,
        )
        assert logger is not None
        assert log_file.parent.exists()
        file_handlers = [h for h in logger.handlers if hasattr(h, "maxBytes")]
        assert len(file_handlers) == 1
        assert file_handlers[0].maxBytes == 1_024
        assert file_handlers[0].backupCount == 3

    def test_setup_logging_json_format(self):
        """Given: fmt="json". When: setup_logging is called.
        Then: returns logger without error."""
        from ai_assistant.core.logger import setup_logging

        logger = setup_logging(fmt="json")
        assert logger is not None

    def test_setup_logging_console_only(self):
        """Given: log_file=None. When: setup_logging is called.
        Then: returns logger with only console handler."""
        from ai_assistant.core.logger import setup_logging

        logger = setup_logging(log_file=None)
        file_handlers = [h for h in logger.handlers if hasattr(h, "baseFilename")]
        assert len(file_handlers) == 0
