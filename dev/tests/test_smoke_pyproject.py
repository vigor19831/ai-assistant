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
            str(Path(__file__).parent.parent.parent),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "ruff check failed: " + result.stdout


def test_pyproject_toml():
    """Verify pyproject.toml has correct settings."""
    import tomllib

    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
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

    # Check frozen versions
    deps = data["project"]["dependencies"]
    assert any("fastapi>=0.110.0,<1.0.0" in d for d in deps)
    assert any("pydantic>=2.7.0,<3.0.0" in d for d in deps)
    assert any("uvicorn[standard]>=0.29.0,<1.0.0" in d for d in deps)
    assert any("httpx>=0.27.0,<1.0.0" in d for d in deps)
    assert any("sqlalchemy[asyncio]>=2.0.0,<3.0.0" in d for d in deps)


def test_all_python_files_compile():
    """Verify all modified Python files compile without syntax errors."""
    import py_compile

    base = Path(__file__).parent.parent.parent
    files_to_check = [
        "src/ai_assistant/adapters/__init__.py",
        "src/ai_assistant/api/deps.py",
        "src/ai_assistant/api/lifespan.py",
        "src/ai_assistant/api/security.py",
        "src/ai_assistant/core/domain/pipeline.py",
        "src/ai_assistant/core/io_utils.py",
        "src/ai_assistant/core/metrics.py",
        "src/ai_assistant/core/pipeline.py",
        "src/ai_assistant/core/ports/chunker.py",
        "src/ai_assistant/core/ports/llm.py",
        "src/ai_assistant/core/ports/reranker.py",
        "src/ai_assistant/core/ports/vector_store.py",
        "src/ai_assistant/core/registry.py",
        "src/ai_assistant/core/retry.py",
        "src/ai_assistant/core/tool_registry.py",
        "src/ai_assistant/features/chat/handlers.py",
        "src/ai_assistant/features/image_analysis/handlers.py",
        "src/ai_assistant/features/rag/handlers.py",
        "src/ai_assistant/main.py",
        "src/ai_assistant/pipeline/decorators.py",
        "src/ai_assistant/pipeline/steps.py",
    ]

    for rel_path in files_to_check:
        f = base / rel_path
        py_compile.compile(str(f), doraise=True)
