#!/usr/bin/env python3
"""
context_build.py — Build AI context document for the project.

Modes:
  super    — Rules + P0 signatures only. Ultra-compact for daily tasks.
             Excludes: implementations, tests, adapters, scripts.
  compact  — P0 full code + P1 AST signatures + P2 inventory.
             Excludes: .git, venv, data, documents, vendor.
  full     — Absolute everything (warning: huge; auto-falls back to compact if >16k Python LOC).

Output: dev/context_build_{mode}.md (relative to project root).
"""

import argparse
import ast
import fnmatch
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("context_build")


# CONFIGURATION

EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    ".env",
    "data",
    "documents",
    "vendor",
    "node_modules",
    ".idea",
    ".vscode",
    "dist",
    "build",
})

ALWAYS_SKIP_PATTERNS: list[str] = [
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
    "*.gguf",
    "*.bin",
    "*.pt",
    "*.pth",
    "*.onnx",
    "*.safetensors",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.gif",
    "*.webp",
    "*.mp3",
    "*.wav",
    "*.pid",
    "*.lock",
    ".DS_Store",
    "Thumbs.db",
    "*.egg-info",
    "*context_build_*.md",
    "dev/TODO.md",
    "dev/TODO_DONE.md",
    "tests_run_*.log",
]

# Patterns that match only basename
BASENAME_SKIP_PATTERNS: frozenset[str] = frozenset({
    "*.pyc", "*.pyo", "*.so", "*.dylib", "*.dll", "*.exe",
    "*.gguf", "*.bin", "*.pt", "*.pth", "*.onnx", "*.safetensors",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp",
    "*.mp3", "*.wav", "*.pid", "*.lock",
    ".DS_Store", "Thumbs.db", "*.egg-info",
})

# Patterns that match full relative path
PATH_SKIP_PATTERNS: frozenset[str] = frozenset({
    "*context_build_*.md", "dev/README_DEV.md", "dev/TODO.md", "tests_run_*.log",
})


# P0: Critical — contracts, API, domain, entry point, config, core implementation
CRITICAL_PATTERNS: list[str] = [
    "config.yaml",
    "pyproject.toml",
    ".gitignore",
    "src/ai_assistant/__init__.py",
    "src/ai_assistant/core/**/*.py",
    "src/ai_assistant/core/prompts/**/*.j2",
    "src/ai_assistant/main.py",
    "src/ai_assistant/registry.py",
    "src/ai_assistant/tool_registry.py",
    "src/ai_assistant/api/**/*.py",
    "src/ai_assistant/features/**/handlers.py",
    "src/ai_assistant/features/**/schemas.py",
    "src/ai_assistant/pipeline/**/*.py",
    "src/ai_assistant/adapters/__init__.py",
    "dev/launcher.py",
    "dev/tests/conftest.py",
    "dev/tests/config.test.yaml",
    "dev/tests/__init__.py",
]

# P0-SUPER: Ultra-compact — only signatures and contracts, no implementations
SUPER_PATTERNS: list[str] = [
    "config.yaml",
    "pyproject.toml",
    "src/ai_assistant/core/domain/**/*.py",
    "src/ai_assistant/core/ports/**/*.py",
    "src/ai_assistant/core/pipeline.py",
    "src/ai_assistant/core/registry.py",
    "src/ai_assistant/core/retry.py",
    "src/ai_assistant/core/circuit_breaker.py",
    "src/ai_assistant/core/config.py",
    "src/ai_assistant/core/constants.py",
    "src/ai_assistant/api/deps.py",
    "src/ai_assistant/api/router.py",
    "src/ai_assistant/api/lifespan.py",
    "src/ai_assistant/api/security.py",
    "src/ai_assistant/main.py",
    "src/ai_assistant/__init__.py",
    "src/ai_assistant/adapters/__init__.py",
    "src/ai_assistant/features/**/schemas.py",
    "src/ai_assistant/pipeline/decorators.py",
]

# P1: Adapters and tests — AST signatures with 🔒 markers
SIGNATURE_PATTERNS: list[str] = [
    "src/ai_assistant/adapters/*.py",
    "src/ai_assistant/features/**/manager.py",
    "dev/tests/test_*.py",
    "dev/scripts/*.py",
    "ops/scripts/*.py",
]


KNOWN_UNKNOWNS: list[tuple[str, str]] = [
    (
        "src/ai_assistant/adapters/llm_openai_compatible.py",
        "SSE parsing, retry logic, tool call extraction, JSON schema validation",
    ),
    (
        "src/ai_assistant/adapters/vector_store_faiss.py",
        "FAISS index format, namespace isolation, persistence, version validation",
    ),
    (
        "src/ai_assistant/adapters/storage_sqlite.py",
        "SQL schema, migrations, async wrapper, transaction handling",
    ),
    (
        "src/ai_assistant/adapters/memory_sqlite.py",
        "Schema design, embedding storage, semantic search SQL",
    ),
    (
        "src/ai_assistant/adapters/tools_calculator.py",
        "JSON schema validation, sandbox execution, error handling",
    ),
    (
        "src/ai_assistant/adapters/embedder_openai_compatible.py",
        "HTTP batching, dimension validation, timeout handling",
    ),
    (
        "src/ai_assistant/core/utils.py",
        "tiktoken vs HF tokenizer fallback, token counting heuristics",
    ),
    (
        "src/ai_assistant/core/metrics.py",
        "Async queue, background worker, graceful shutdown",
    ),
    (
        "src/ai_assistant/core/io_utils.py",
        "Atomic write, fsync, cross-platform temp file handling",
    ),
    (
        "src/ai_assistant/api/lifespan.py",
        "Startup sequencing, shutdown cleanup, PID management",
    ),
    (
        "src/ai_assistant/api/router.py",
        "Dynamic import, error handling, dependency injection",
    ),
    (
        "dev/tests/test_contracts.py",
        "Port contract validation, adapter compliance checks",
    ),
    (
        "dev/tests/test_core_critical.py",
        "Core immutability, PipelineData mutation guards",
    ),
    (
        "dev/tests/test_resilience.py",
        "Retry behavior, circuit breaker, timeout handling",
    ),
    (
        "dev/tests/test_security.py",
        "API key validation, rate limiting, request size limits",
    ),
    (
        "dev/launcher.py",
        "Menu system, background process, terminal spawning, log rotation",
    ),
]

ALREADY_EMBEDDED: frozenset[str] = frozenset({"README.md", "dev/AI_RULES.md"})

DEFAULT_OUTPUT: dict[str, str] = {
    "compact": "context_build_compact.md",
    "full": "context_build_full.md",
    "super": "context_build_super.md",
}

ENV_PRIORITY_BLOCK: str = """## 🌍 Env Priority

Configuration resolution order (highest to lowest priority):

| Priority | Source | Example |
|----------|--------|---------|
| 1 | Environment variable | `AI_LLM_API_BASE=http://...` |
| 2 | `config.yaml` | `llm.api_base: http://...` |
| 3 | Hard-coded default | `http://127.0.0.1:8080/v1` |

> **Rule:** Always prefer env vars for secrets and deployment-specific overrides.
> Never commit API keys to `config.yaml`.
"""



# HELPERS


def find_project_root() -> Path:
    """Find project root: directory that contains README.md (and preferably pyproject.toml)."""
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, *script_dir.parents]:
        has_readme = (parent / "README.md").exists()
        has_pyproject = (parent / "pyproject.toml").exists()
        if has_readme and has_pyproject:
            return parent
        if has_readme:
            return parent
    # Ultimate fallback: parent of dev/scripts/
    return script_dir.parent.parent


def should_skip_file(rel_path: str) -> bool:
    basename = os.path.basename(rel_path)
    for pat in ALWAYS_SKIP_PATTERNS:
        if pat in BASENAME_SKIP_PATTERNS:
            if fnmatch.fnmatch(basename, pat):
                return True
        else:
            if fnmatch.fnmatch(rel_path, pat):
                return True
    return False


def _get_ext(rel_path: str) -> str:
    """Determine markdown code block language from file extension."""
    suffix_map = {
        ".py": "python",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".j2": "jinja2",
    }
    return suffix_map.get(Path(rel_path).suffix, "text")


def resolve_patterns(root: Path, patterns: list[str]) -> set[str]:
    """Resolve glob patterns to a set of relative POSIX paths."""
    matched: set[str] = set()
    for pat in patterns:
        if "**" in pat or "*" in pat:
            for p in root.glob(pat):
                if p.is_file():
                    matched.add(p.relative_to(root).as_posix())
        else:
            p = root / pat
            if p.is_file():
                matched.add(p.relative_to(root).as_posix())
            elif p.is_dir():
                for child in p.rglob("*"):
                    if child.is_file():
                        matched.add(child.relative_to(root).as_posix())
    return matched


def count_loc(text: str) -> int:
    """Count non-empty lines (crude, for non-Python files)."""
    return sum(1 for line in text.splitlines() if line.strip())


def count_python_loc(text: str) -> int:
    """Count non-empty, non-comment, non-docstring lines in Python source."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return count_loc(text)

    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node)
            if doc:
                start = node.body[0].lineno
                end = node.body[0].end_lineno or start
                for i in range(start, end + 1):
                    docstring_lines.add(i)

    loc = 0
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if i in docstring_lines:
            continue
        loc += 1
    return loc


def _is_known_unknown(rel_path: str) -> str | None:
    for path, hint in KNOWN_UNKNOWNS:
        if rel_path == path:
            return hint
    return None


def _extract_tags(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> list[str]:
    """Extract minimal semantic tags from decorators."""
    tags: list[str] = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            if dec.id == "with_retry":
                tags.append("# with_retry")
            elif dec.id == "register":
                tags.append("# register")
    return tags



def extract_api_surface(source: str, rel_path: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"# ⚠️ Syntax error in {rel_path}: {exc}\n"

    lines: list[str] = [f"# API Surface: {rel_path}", ""]

    unknown_hint = _is_known_unknown(rel_path)
    if unknown_hint:
        lines.append(f"# 🔒 KNOWN UNKNOWN: {unknown_hint}")
        lines.append(f"#    To see implementation: 🔍 REQUEST CODE: `{rel_path}`")
        lines.append("")

    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        lines.append(f'"""{mod_doc[:500]}"""')
        lines.append("")

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            try:
                lines.append(ast.unparse(node))
            except Exception:
                pass

        elif isinstance(node, ast.ClassDef):
            bases = [ast.unparse(b) for b in node.bases] if node.bases else []
            base_str = f"({', '.join(bases)})" if bases else ""
            doc = ast.get_docstring(node)
            if doc:
                doc_line = "\n    " + f'"""{doc[:300]}"""'
            else:
                doc_line = ""
            decs = "\n".join(f"@{ast.unparse(d)}" for d in node.decorator_list)
            prefix = (decs + "\n") if decs else ""
            tags = _extract_tags(node)
            tag_str = f"  {'  '.join(tags)}" if tags else ""

            # Mark non-ABC classes as having hidden implementation
            is_abc = any(ast.unparse(b) == "ABC" for b in node.bases)
            impl_tag = "" if is_abc else "  # 🔒 impl hidden"

            lines.append(f"{prefix}class {node.name}{base_str}:{doc_line}{tag_str}{impl_tag}")
            lines.append("")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                args = ast.unparse(node.args)
            except Exception:
                args = "..."
            doc = ast.get_docstring(node)
            if doc:
                doc_line = "\n    " + f'"""{doc[:300]}"""'
            else:
                doc_line = ""
            decs = "\n".join(f"@{ast.unparse(d)}" for d in node.decorator_list)
            prefix = (decs + "\n") if decs else ""
            async_p = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            tags = _extract_tags(node)
            tag_str = f"  {'  '.join(tags)}" if tags else ""

            # No # 🔒 impl hidden for top-level functions — file-level hint is enough
            lines.append(
                f"{prefix}{async_p}def {node.name}({args}):{doc_line}{tag_str}"
            )
            lines.append("")

        elif isinstance(node, ast.Assign):
            try:
                if all(
                    isinstance(t, ast.Name) and t.id.isupper() for t in node.targets
                ):
                    lines.append(ast.unparse(node))
            except Exception:
                pass
        elif isinstance(node, ast.AnnAssign):
            try:
                if isinstance(node.target, ast.Name) and node.target.id.isupper():
                    lines.append(ast.unparse(node))
            except Exception:
                pass

    return "\n".join(lines)



def get_excluded_manifest(root: Path) -> list[tuple[str, str, list[str]]]:
    manifests: list[tuple[str, str, list[str]]] = []
    purposes = {
        "data": "Indexed documents, tokenizers, metrics, PID files",
        "documents": "Source documents for RAG indexing (personal, work, other)",
        "vendor": "Local LLM models (GGUF), llama.cpp binaries",
        ".git": "Git version control metadata",
    }
    for name in sorted({"data", "documents", "vendor", ".git"}):
        p = root / name
        if not p.exists():
            continue
        items: list[str] = []
        try:
            for child in sorted(p.iterdir()):
                items.append(f"{child.name}/" if child.is_dir() else child.name)
        except PermissionError:
            items = ["[permission denied]"]
        manifests.append((name, purposes.get(name, "Project directory"), items))
    return manifests


def get_file_group(rel_path: str) -> str:
    if rel_path in ("config.yaml", "pyproject.toml", ".gitignore"):
        return "📋 Project Config & Manifests"
    if rel_path.startswith("src/ai_assistant/core/"):
        return "🧠 Core Contracts & Domain"
    if rel_path.startswith("src/ai_assistant/api/"):
        return "🔌 API Layer"
    if rel_path.startswith("src/ai_assistant/features/"):
        return "✨ Features"
    if rel_path.startswith("src/ai_assistant/pipeline/"):
        return "⚡ Pipeline"
    if rel_path.startswith("src/ai_assistant/adapters/"):
        return "🔌 Adapters"
    if rel_path in (
        "src/ai_assistant/main.py",
        "src/ai_assistant/registry.py",
        "src/ai_assistant/tool_registry.py",
        "src/ai_assistant/__init__.py",
    ):
        return "🚀 Entry Points & Registry"
    if rel_path.startswith("dev/"):
        return "🛠️ Development & Tests"
    if rel_path.startswith("ops/"):
        return "⚙️ Operations"
    return "📦 Other"


def _is_dir_excluded(dirpath: str, root: Path) -> bool:
    """Check if any component of the relative directory path is excluded."""
    rel_dir = os.path.relpath(dirpath, root)
    if rel_dir == ".":
        return False
    return any(part in EXCLUDED_DIRS for part in Path(rel_dir).parts)



# SCAN & BUILD


def scan_project(
    root: Path, mode: str
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str | None]], dict]:
    if mode == "super":
        critical_set = resolve_patterns(root, SUPER_PATTERNS)
        signature_set: set[str] = set()
    else:
        critical_set = resolve_patterns(root, CRITICAL_PATTERNS)
        signature_set = resolve_patterns(root, SIGNATURE_PATTERNS)

    critical_files: list[tuple[str, str]] = []
    signature_files: list[tuple[str, str]] = []
    other_files: list[tuple[str, str | None]] = []
    metrics = {"total_files": 0, "py_files": 0, "total_loc": 0, "py_loc": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude directories by full relative path, not just basename
        dirnames[:] = [
            d for d in dirnames
            if not _is_dir_excluded(os.path.join(dirpath, d), root)
        ]

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel = fpath.relative_to(root).as_posix()

            if should_skip_file(rel):
                continue

            metrics["total_files"] += 1

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                loc = count_python_loc(content) if rel.endswith(".py") else count_loc(content)
                metrics["total_loc"] += loc
            except OSError:
                content = ""
                loc = 0

            if rel.endswith(".py"):
                metrics["py_files"] += 1
                metrics["py_loc"] += loc

            if rel in critical_set:
                critical_files.append((rel, content))
            elif mode == "super":
                other_files.append((rel, None))
            elif rel in signature_set and rel.endswith(".py"):
                signature_files.append((rel, content))
                if mode == "full":
                    other_files.append((rel, content))
            else:
                if mode == "full":
                    other_files.append((rel, content))
                else:
                    other_files.append((rel, None))

    return critical_files, signature_files, other_files, metrics



def build_markdown(
    root: Path,
    mode: str,
    critical: list[tuple[str, str]],
    signature: list[tuple[str, str]],
    other: list[tuple[str, str | None]],
    metrics: dict,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    readme_path = root / "README.md"
    readme = (
        readme_path.read_text(encoding="utf-8", errors="replace")
        if readme_path.exists()
        else "*README.md not found*"
    )

    airules_path = root / "dev" / "AI_RULES.md"
    airules = (
        airules_path.read_text(encoding="utf-8", errors="replace")
        if airules_path.exists()
        else "*AI_RULES.md not found*"
    )

    readme_dev_path = root / "dev" / "README_DEV.md"
    readme_dev = (
        readme_dev_path.read_text(encoding="utf-8", errors="replace")
        if readme_dev_path.exists()
        else "*README_DEV.md not found*"
    )

    excluded_manifests = get_excluded_manifest(root)

    lines: list[str] = []

    # Header
    lines.extend([
        "# AI Context: AI Assistant",
        f"> **Generated:** {now}",
        f"> **Mode:** `{mode}`",
        f"> **Root:** `{root}`",
        f"> **Metrics:** {metrics['total_files']} files | {metrics['py_files']} Python files | {metrics['py_loc']:,} Python LOC",
        "",
        "---",
        "",
    ])

    # 1. AI RULES
    lines.extend([
        "## 🚨 AI DEVELOPMENT GUIDELINES — READ FIRST",
        "> Auto-extracted from: `dev/AI_RULES.md`",
        "> ⚠️ **These rules override general assumptions. Review before proposing any change.**",
        "",
        "```markdown",
        airules,
        "```",
        "",
        "---",
        "",
    ])

    # 2. README
    lines.extend([
        "## 📋 PROJECT OVERVIEW",
        "> Auto-extracted from: `README.md`",
        "",
        "```markdown",
        readme,
        "```",
        "",
        "---",
        "",
    ])

    # 3. README_DEV
    lines.extend([
        "## 🛠️ DEVELOPER WORKSPACE",
        "> Auto-extracted from: `dev/README_DEV.md`",
        "> **Workflow, scripts, troubleshooting for solo development.**",
        "",
        "```markdown",
        readme_dev,
        "```",
        "",
        "---",
        "",
    ])

    # 4. Env Priority
    lines.append(ENV_PRIORITY_BLOCK)
    lines.extend(["", "---", ""])

    # 5. Structure
    lines.extend([
        "## 🗂️ PROJECT STRUCTURE",
        "",
        "### Included Files",
    ])
    included = {r for r, _ in critical}
    if mode in ("compact", "super"):
        included.update(r for r, _ in signature)
        included.update(r for r, c in other if c is not None)
    else:
        included.update(r for r, c in other if c is not None)
    for r in sorted(included):
        lines.append(f"- `{r}`")
    lines.append("")

    lines.extend([
        "### Excluded Directories (Known to Exist)",
        "| Directory | Purpose | Top-Level Contents |",
        "|-----------|---------|-------------------|",
    ])
    for name, purpose, items in excluded_manifests:
        display = ", ".join(items[:12])
        if len(items) > 12:
            display += f" … (+{len(items) - 12})"
        lines.append(f"| `{name}/` | {purpose} | {display} |")
    lines.extend(["", "---", ""])

    # 6. Critical Code (P0)
    lines.extend([
        "## 🔑 CRITICAL SOURCE CODE (P0)",
        "> Full content. These files define contracts, API surface, features, and entry points.",
        "> **Never modify without checking downstream adapters and tests.**",
        "",
    ])

    current_group = ""
    for rel, content in sorted(critical, key=lambda x: x[0]):
        if rel in ALREADY_EMBEDDED:
            continue
        group = get_file_group(rel)
        if group != current_group:
            lines.append(f"### {group}")
            current_group = group

        if "class PipelineData" in content:
            lines.append(
                "> ⚠️ **DO NOT MUTATE PipelineData in-place.** Always return new instances from pipeline steps."
            )
            lines.append("")

        lines.append(f"#### `{rel}`")
        lines.append(f"```{_get_ext(rel)}")
        lines.append(content or "# [could not read file]")
        lines.append("```")
        lines.append("")

    # 7. Signatures (P1)
    if mode in ("compact", "super") and signature:
        lines.extend([
            "---",
            "",
            "## 🧩 ADAPTER & TEST SIGNATURES (P1)",
            "> Public API surface extracted via AST. Contains imports, classes, functions, docstrings, and inline semantic tags.",
            "> **🔒 = implementation hidden. To see full code, use the request protocol below.**",
            "",
        ])

        for rel, content in sorted(signature, key=lambda x: x[0]):
            api_surface = extract_api_surface(content, rel)
            lines.append(f"### `{rel}`")
            lines.append("```python")
            lines.append(api_surface)
            lines.append("```")
            lines.append("")

    # 8. Inventory / Full remainder
    if other:
        lines.extend(["---", ""])
        if mode == "compact":
            lines.extend([
                "## 📦 FILE INVENTORY (P2 — Excluded from Compact Context)",
                "> These files exist but are omitted to save context space.",
                "> Request full content only when implementation details matter.",
                "",
                "| File | Group | Type | Size (chars) |",
                "|------|-------|------|-------------|",
            ])
            for rel, content in sorted(other, key=lambda x: x[0]):
                size = len(content) if content else "N/A"
                ftype = (
                    "Python" if rel.endswith(".py")
                    else "Config" if rel.endswith((".yaml", ".toml", ".json"))
                    else "Other"
                )
                group = get_file_group(rel)
                lines.append(f"| `{rel}` | {group} | {ftype} | {size} |")
            lines.append("")
        else:
            lines.extend([
                "## 📝 ALL REMAINING FILES (Full Mode)",
            ])
            for rel, content in sorted(other, key=lambda x: x[0]):
                if content is None or rel in ALREADY_EMBEDDED:
                    continue
                lines.append(f"### `{rel}`")
                lines.append(f"```{_get_ext(rel)}")
                lines.append(content)
                lines.append("```")
                lines.append("")

    # 9. Error Taxonomy
    taxonomy_path = root / "dev" / "ERROR_TAXONOMY.md"
    if taxonomy_path.exists() and mode != "super":
        lines.extend([
            "---",
            "",
            taxonomy_path.read_text(encoding="utf-8", errors="replace"),
            "",
        ])

    # 10. Known Unknowns
    lines.extend([
        "---",
        "",
        "## ❓ KNOWN UNKNOWNS — Request Before Modifying",
        "> These files contain complex logic hidden in P2. You MUST request them before proposing changes.",
        "> **Do NOT guess implementation details, error types, or edge case handling.**",
        "",
        "| File | Hidden Complexity | Request Trigger |",
        "|------|-----------------|---------------|",
    ])
    for path, hint in KNOWN_UNKNOWNS:
        group = get_file_group(path)
        trigger = (
            "Before modifying tested component" if "test" in path
            else "Any change to this component or its consumers"
        )
        lines.append(f"| `{path}` | {hint} | {trigger} |")
    lines.append("")

    # 11. Request Protocol
    lines.extend([
        "---",
        "",
        "## 🚨 OBLIGATORY REQUEST PROTOCOL",
        "",
        "You MUST NOT guess implementation details. If you need to:",
        "- Verify error handling, retry logic, or edge cases",
        "- See actual HTTP call construction, JSON parsing, or SSE handling",
        "- Check database schema, SQL queries, or migration logic",
        "- Review test assertions before proposing changes",
        "- Copy-paste or refactor existing code",
        "- Understand any file marked with 🔒 or listed in Known Unknowns",
        "",
        "Then output **EXACTLY**:",
        "",
        "```",
        "🔍 REQUEST CODE: `relative/path/to/file.py`",
        "Reason: [1-sentence justification]",
        "```",
        "",
        "**Forbidden:** Inventing method bodies, assuming exception types, hallucinating config keys, or guessing retry strategies. When in doubt — REQUEST.",
        "",
        "### Priority Rules for Compact Mode",
        "1. **Always check P0/P1 first** — the public API is usually enough for architecture discussions.",
        "2. **Request code when:**",
        "   - You need to see implementation logic (not just interface)",
        "   - You need to verify how an adapter handles edge cases",
        "   - You need to copy-paste or refactor existing code",
        "   - The file is in Known Unknowns or marked with 🔒",
        "3. **Batch requests** — ask for multiple files in one block if needed",
        "",
    ])

    return "\n".join(lines)



# MAIN


def main() -> int:
    # Auto-update ERROR_TAXONOMY.md
    try:
        script_dir = Path(__file__).resolve().parent
        taxonomy_script = script_dir / "error_taxonomy_build.py"
        if taxonomy_script.exists():
            result = subprocess.run(
                [sys.executable, str(taxonomy_script)],
                capture_output=True,
                text=True,
                cwd=find_project_root(),
                timeout=60,
            )
            if result.returncode == 0:
                logger.info("ERROR_TAXONOMY.md auto-updated")
            else:
                logger.warning("Taxonomy update failed: %s", result.stderr)
        else:
            logger.info("error_taxonomy_build.py not found, skipping auto-update")
    except subprocess.TimeoutExpired:
        logger.warning("Taxonomy update timed out after 60s")
    except Exception as exc:
        logger.warning("Could not auto-update taxonomy: %s", exc)

    parser = argparse.ArgumentParser(
        description="Build AI context document for the project."
    )
    parser.add_argument(
        "--mode",
        choices=["compact", "full", "super"],
        default="compact",
        help="compact: critical + signatures + inventory. full: everything. super: rules + signatures only.",
    )
    parser.add_argument(
        "--full",
        action="store_const",
        dest="mode",
        const="full",
        help="Shorthand for --mode full",
    )
    parser.add_argument(
        "--compact",
        action="store_const",
        dest="mode",
        const="compact",
        help="Shorthand for --mode compact",
    )
    parser.add_argument(
        "--super",
        action="store_const",
        dest="mode",
        const="super",
        help="Shorthand for --mode super",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output filename relative to project root. Defaults to context_build_<mode>.md",
    )
    args = parser.parse_args()

    root = find_project_root()

    # Sanity check: if script is in dev/scripts/, root should be grandparent
    script_parent = Path(__file__).resolve().parent
    if script_parent.name == "scripts" and script_parent.parent.name == "dev":
        expected_root = script_parent.parent.parent
        if root != expected_root and expected_root.exists():
            logger.info("Adjusting root from %s to %s", root, expected_root)
            root = expected_root

    logger.info("Project root: %s", root)
    logger.info("Mode: %s", args.mode)

    critical, signature, other, metrics = scan_project(root, args.mode)

    logger.info("Metrics: %s", metrics)
    logger.info("P0 critical files: %d", len(critical))
    logger.info("P1 signature files: %d", len(signature))
    logger.info("P2/other files: %d", len(other))

    if args.mode == "full" and metrics["py_loc"] > 16000:
        logger.warning("Context too large (%d Python LOC > 16,000). Auto-falling back to compact mode.", metrics["py_loc"])
        args.mode = "compact"

    out_name = args.output or DEFAULT_OUTPUT[args.mode]
    md = build_markdown(root, args.mode, critical, signature, other, metrics)

    dev_dir = root / "dev"
    dev_dir.mkdir(parents=True, exist_ok=True)
    out_path = dev_dir / out_name
    out_path.write_text(md, encoding="utf-8")

    logger.info("Written: %s (%d chars)", out_path.relative_to(root), len(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
