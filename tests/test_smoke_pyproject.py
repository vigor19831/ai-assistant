"""Smoke tests for pyproject.toml changes — no conftest dependencies."""

import sys
from pathlib import Path

import pytest


def test_ruff_rules():
    """Verify ruff check passes."""
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            str(Path(__file__).parent.parent),
        ],
        capture_output=True,
        text=True,
    )
    stdout = result.stdout or ""
    assert result.returncode == 0, "ruff check failed: " + stdout


def test_pyproject_toml():
    """Verify pyproject.toml has correct settings."""
    import tomllib

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    # Check ruff select includes new rules
    ruff_select = data["tool"]["ruff"]["lint"]["select"]
    assert "B" in ruff_select
    assert "SIM" in ruff_select
    assert "C4" in ruff_select
    assert "TCH" in ruff_select

    # Check mypy strict
    assert data["tool"]["mypy"]["strict"] is True

    # Check frozen versions using PEP 508 parsing
    from packaging.requirements import Requirement

    deps = [Requirement(d) for d in data["project"]["dependencies"]]

    def assert_dep(
        name: str,
        lower: str,
        upper: str,
        extras: set[str] | None = None,
    ) -> None:
        for req in deps:
            if req.name == name:
                spec = str(req.specifier)
                assert f">={lower}" in spec, f"{name} missing lower bound {lower}"
                assert f"<{upper}" in spec, f"{name} missing upper bound {upper}"
                if extras is not None:
                    assert req.extras == extras, f"{name} extras mismatch"
                return
        raise AssertionError(f"{name} not found in dependencies")

    assert_dep("fastapi", "0.110.0", "1.0.0")
    assert_dep("pydantic", "2.7.0", "3.0.0")
    assert_dep("uvicorn", "0.29.0", "1.0.0", extras={"standard"})
    assert_dep("httpx", "0.27.0", "1.0.0")
    assert_dep("sqlalchemy", "2.0.0", "3.0.0", extras={"asyncio"})


def test_all_python_files_compile():
    """Verify all modified Python files compile without syntax errors."""
    import py_compile

    base = Path(__file__).parent.parent
    files_to_check = [
        "src/ai_assistant/adapters/__init__.py",
        "src/ai_assistant/api/deps.py",
        "src/ai_assistant/api/lifespan.py",
        "src/ai_assistant/api/security.py",
        "src/ai_assistant/core/domain/pipeline.py",
        "src/ai_assistant/core/io_utils.py",
        "src/ai_assistant/core/pipeline.py",
        "src/ai_assistant/core/ports/chunker.py",
        "src/ai_assistant/core/ports/llm.py",
        "src/ai_assistant/core/ports/reranker.py",
        "src/ai_assistant/core/ports/vector_store.py",
        "src/ai_assistant/core/retry.py",
        "src/ai_assistant/features/chat/handlers.py",
        "src/ai_assistant/features/rag/handlers.py",
        "src/ai_assistant/main.py",
        "src/ai_assistant/api/static.py",
        "src/ai_assistant/core/pipeline_steps.py",
    ]

    for rel_path in files_to_check:
        f = base / rel_path
        py_compile.compile(str(f), doraise=True)


def test_chat_manager_imported_at_module_level():
    """ChatManager must be imported at top-level in deps.py — no deferred imports."""
    from ai_assistant.api import deps

    assert hasattr(deps, "ChatManager"), (
        "ChatManager is not imported at top-level in deps.py — "
        "deferred import detected"
    )


def test_lifespan_does_not_import_main():
    """lifespan.py must not import from entry point to avoid circular dependency."""
    import inspect
    from ai_assistant.api import lifespan

    source = inspect.getsource(lifespan)
    assert "from ai_assistant.main import" not in source, (
        "lifespan.py imports from main.py — circular entry point dependency"
    )


def test_mount_static_in_api_layer():
    """_mount_static must live in api.static, not in entry point."""
    from ai_assistant.api.static import _mount_static

    assert callable(_mount_static)


def test_key_modules_import_without_cycles():
    """Top-level imports of all key modules must succeed immediately (no deferred cycles)."""
    import ai_assistant.api.static
    import ai_assistant.api.lifespan
    import ai_assistant.api.deps
    import ai_assistant.main
