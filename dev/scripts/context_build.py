#!/usr/bin/env python3
"""
context_build.py — Build AI context document for the project.

Modes:
  compact  — P0 full code + P1 AST signatures + P2 inventory.
             Excludes: .git, venv, data, documents, vendor.
  full     — Absolute everything (warning: huge; auto-falls back to compact if >16k Python LOC).

Output: dev/context_build_{mode}.md (relative to project root).
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

EXCLUDED_DIRS: Set[str] = {
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
}

ALWAYS_SKIP_PATTERNS: List[str] = [
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
    "*context_build_compact.md",
    "*context_build_full.md",
    "dev/README_DEV.md",
    "dev/TODO.md",
]

# P0: Critical — contracts, API, domain, entry point, config, core implementation
CRITICAL_PATTERNS: List[str] = [
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

# P1: Adapters and tests — AST signatures with 🔒 markers
SIGNATURE_PATTERNS: List[str] = [
    "src/ai_assistant/adapters/*.py",
    "src/ai_assistant/features/**/manager.py",
    "dev/tests/test_*.py",
    "dev/scripts/*.py",
    "ops/scripts/*.py",
]

# Known unknowns: files with hidden complexity that AI MUST request before modifying
KNOWN_UNKNOWNS: List[Tuple[str, str]] = [
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

ALREADY_EMBEDDED: Set[str] = {"README.md", "dev/AI_RULES.md"}

DEFAULT_OUTPUT: Dict[str, str] = {
    "compact": "context_build_compact.md",
    "full": "context_build_full.md",
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

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────


def find_project_root() -> Path:
    """Find project root: directory that contains BOTH README.md and pyproject.toml."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "README.md").exists() and (parent / "pyproject.toml").exists():
            return parent
    # Fallback: at least README.md
    for parent in [current, *current.parents]:
        if (parent / "README.md").exists():
            return parent
    return current.parent.parent


def should_skip_file(rel_path: str) -> bool:
    basename = os.path.basename(rel_path)
    for pat in ALWAYS_SKIP_PATTERNS:
        if fnmatch.fnmatch(rel_path, pat) or fnmatch.fnmatch(basename, pat):
            return True
    return False


def resolve_patterns(root: Path, patterns: List[str]) -> Set[str]:
    matched: Set[str] = set()
    for pat in patterns:
        pat_os = pat.replace("/", os.sep)
        if "**" in pat:
            for p in root.glob(pat_os):
                if p.is_file():
                    matched.add(os.path.relpath(p, root).replace(os.sep, "/"))
        else:
            p = root / pat_os
            if p.exists() and p.is_file():
                matched.add(pat)
            elif p.exists() and p.is_dir():
                for child in p.rglob("*"):
                    if child.is_file():
                        matched.add(os.path.relpath(child, root).replace(os.sep, "/"))
    return matched


def count_loc(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def _extract_tags(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> List[str]:
    """Extract inline semantic tags from decorators and naming heuristics."""
    tags: List[str] = []
    name = getattr(node, "name", "")

    for dec in node.decorator_list:
        dec_str = ast.unparse(dec)
        if "with_retry" in dec_str:
            tags.append(f"# {dec_str}")
        elif "register" in dec_str:
            tags.append(f"# {dec_str}")

    lower = name.lower()
    if lower.startswith(("validate", "check", "verify")):
        tags.append("# validates input")
    if "embed" in lower or "encode" in lower:
        try:
            args_str = ast.unparse(node.args)
            if "dim" in args_str:
                tags.append("# validates dim")
        except Exception:
            pass
    if "sse" in lower or ("stream" in lower and "parse" in lower):
        tags.append("# handles SSE parsing")
    if "retry" in lower and "with_retry" not in " ".join(tags):
        tags.append("# retry logic")

    return tags


def _is_known_unknown(rel_path: str) -> str | None:
    """Check if file is a known unknown and return hint."""
    for path, hint in KNOWN_UNKNOWNS:
        if rel_path == path:
            return hint
    return None


# Methods that typically have hidden complex implementation
_HIDDEN_IMPL_METHODS: Set[str] = {
    "complete",
    "stream",
    "embed",
    "rerank",
    "describe",
    "transcribe",
    "synthesize",
    "add",
    "search",
    "delete",
    "save",
    "load",
    "list_by_filter",
    "list_namespaces",
    "execute",
    "dispatch",
    "chunk",
    "shutdown",
    "init_db",
    "transcribe",
    "synthesize",
    "analyze",
    "index_documents",
    "query",
    "health",
    "run",
    "start",
    "stop",
}


def extract_api_surface(source: str, rel_path: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"# ⚠️ Syntax error in {rel_path}: {exc}\n"

    lines: List[str] = [f"# API Surface: {rel_path}", ""]

    # Add known unknown hint if applicable
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
            doc_line = f'\n    """{doc[:300]}"""' if doc else ""
            decs = "\n".join(f"@{ast.unparse(d)}" for d in node.decorator_list)
            prefix = (decs + "\n") if decs else ""
            tags = _extract_tags(node)
            tag_str = f"  {'  '.join(tags)}" if tags else ""
            lines.append(f"{prefix}class {node.name}{base_str}:{doc_line}{tag_str}")
            lines.append("")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                args = ast.unparse(node.args)
            except Exception:
                args = "..."
            doc = ast.get_docstring(node)
            doc_line = f'\n    """{doc[:300]}"""' if doc else ""
            decs = "\n".join(f"@{ast.unparse(d)}" for d in node.decorator_list)
            prefix = (decs + "\n") if decs else ""
            async_p = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            tags = _extract_tags(node)
            tag_str = f"  {'  '.join(tags)}" if tags else ""

            # Add implementation hidden hint for non-trivial methods
            if node.name in _HIDDEN_IMPL_METHODS:
                tag_str += "  # 🔒 impl hidden"

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


def get_excluded_manifest(root: Path) -> List[Tuple[str, str, List[str]]]:
    manifests: List[Tuple[str, str, List[str]]] = []
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
        items: List[str] = []
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


# ──────────────────────────────────────────────────────────────────────────────
# SCAN & BUILD
# ──────────────────────────────────────────────────────────────────────────────


def scan_project(root: Path, mode: str) -> Tuple[List, List, List, dict]:
    critical_set = resolve_patterns(root, CRITICAL_PATTERNS)
    signature_set = resolve_patterns(root, SIGNATURE_PATTERNS)

    critical_files: List[Tuple[str, str]] = []
    signature_files: List[Tuple[str, str]] = []
    other_files: List[Tuple[str, str | None]] = []
    metrics = {"total_files": 0, "py_files": 0, "total_loc": 0, "py_loc": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel = os.path.relpath(fpath, root).replace(os.sep, "/")

            if should_skip_file(rel):
                continue

            metrics["total_files"] += 1
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                loc = count_loc(content)
                metrics["total_loc"] += loc
            except Exception:
                content = ""
                loc = 0

            if rel.endswith(".py"):
                metrics["py_files"] += 1
                metrics["py_loc"] += loc

            if rel in critical_set:
                critical_files.append((rel, content))
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
    critical: List[Tuple[str, str]],
    signature: List[Tuple[str, str]],
    other: List[Tuple[str, str | None]],
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

    excluded_manifests = get_excluded_manifest(root)

    lines: List[str] = []

    # Header
    lines.append("# AI Context: AI Assistant")
    lines.append(f"> **Generated:** {now}")
    lines.append(f"> **Mode:** `{mode}`")
    lines.append(f"> **Root:** `{root}`")
    lines.append(
        f"> **Metrics:** {metrics['total_files']} files | {metrics['py_files']} Python files | {metrics['py_loc']:,} Python LOC"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # 1. AI RULES
    lines.append("## 🚨 AI DEVELOPMENT GUIDELINES — READ FIRST")
    lines.append("> Auto-extracted from: `dev/AI_RULES.md`")
    lines.append(
        "> ⚠️ **These rules override general assumptions. Review before proposing any change.**"
    )
    lines.append("")
    lines.append("```markdown")
    lines.append(airules)
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 2. README
    lines.append("## 📋 PROJECT OVERVIEW")
    lines.append("> Auto-extracted from: `README.md`")
    lines.append("")
    lines.append("```markdown")
    lines.append(readme)
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 3. Env Priority
    lines.append(ENV_PRIORITY_BLOCK)
    lines.append("")
    lines.append("---")
    lines.append("")

    # 4. Structure
    lines.append("## 🗂️ PROJECT STRUCTURE")
    lines.append("")
    lines.append("### Included Files")
    included = {r for r, _ in critical}
    if mode == "compact":
        included.update(r for r, _ in signature)
    included.update(r for r, _ in other if mode == "full")
    included.update(r for r, c in other if mode == "compact")
    for r in sorted(included):
        lines.append(f"- `{r}`")
    lines.append("")

    lines.append("### Excluded Directories (Known to Exist)")
    lines.append("| Directory | Purpose | Top-Level Contents |")
    lines.append("|-----------|---------|-------------------|")
    for name, purpose, items in excluded_manifests:
        display = ", ".join(items[:12])
        if len(items) > 12:
            display += f" … (+{len(items) - 12})"
        lines.append(f"| `{name}/` | {purpose} | {display} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 5. Critical Code (P0)
    lines.append("## 🔑 CRITICAL SOURCE CODE (P0)")
    lines.append(
        "> Full content. These files define contracts, API surface, features, and entry points."
    )
    lines.append("> **Never modify without checking downstream adapters and tests.**")
    lines.append("")

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

        ext = (
            "python"
            if rel.endswith(".py")
            else (
                "yaml"
                if rel.endswith(".yaml")
                else (
                    "toml"
                    if rel.endswith(".toml")
                    else ("jinja2" if rel.endswith(".j2") else "text")
                )
            )
        )
        lines.append(f"#### `{rel}`")
        lines.append(f"```{ext}")
        lines.append(content or "# [could not read file]")
        lines.append("```")
        lines.append("")

    # 6. Signatures (P1) — compact only
    if mode == "compact" and signature:
        lines.append("---")
        lines.append("")
        lines.append("## 🧩 ADAPTER & TEST SIGNATURES (P1)")
        lines.append(
            "> Public API surface extracted via AST. Contains imports, classes, functions, docstrings, and inline semantic tags."
        )
        lines.append(
            "> **🔒 = implementation hidden. To see full code, use the request protocol below.**"
        )
        lines.append("")

        for rel, content in sorted(signature, key=lambda x: x[0]):
            api_surface = extract_api_surface(content, rel)
            lines.append(f"### `{rel}`")
            lines.append("```python")
            lines.append(api_surface)
            lines.append("```")
            lines.append("")

    # 7. Inventory (P2) / Full remainder
    if other:
        lines.append("---")
        lines.append("")
        if mode == "compact":
            lines.append("## 📦 FILE INVENTORY (P2 — Excluded from Compact Context)")
            lines.append("> These files exist but are omitted to save context space.")
            lines.append(
                "> Request full content only when implementation details matter."
            )
            lines.append("")
            lines.append("| File | Group | Type | Size (chars) |")
            lines.append("|------|-------|------|-------------|")
            for rel, content in sorted(other, key=lambda x: x[0]):
                size = len(content) if content else "N/A"
                ftype = (
                    "Python"
                    if rel.endswith(".py")
                    else "Config"
                    if rel.endswith((".yaml", ".toml", ".json"))
                    else "Other"
                )
                group = get_file_group(rel)
                lines.append(f"| `{rel}` | {group} | {ftype} | {size} |")
            lines.append("")
        else:
            lines.append("## 📝 ALL REMAINING FILES (Full Mode)")
            for rel, content in sorted(other, key=lambda x: x[0]):
                if content is None or rel in ALREADY_EMBEDDED:
                    continue
                ext = "python" if rel.endswith(".py") else "text"
                lines.append(f"### `{rel}`")
                lines.append(f"```{ext}")
                lines.append(content)
                lines.append("```")
                lines.append("")

    # 7.5. Error Taxonomy (auto-injected from dev/ERROR_TAXONOMY.md)
    taxonomy_path = root / "dev" / "ERROR_TAXONOMY.md"
    if taxonomy_path.exists():
        lines.append("---")
        lines.append("")
        lines.append(taxonomy_path.read_text(encoding="utf-8", errors="replace"))
        lines.append("")

    # 8. Known Unknowns
    lines.append("---")
    lines.append("")
    lines.append("## ❓ KNOWN UNKNOWNS — Request Before Modifying")
    lines.append(
        "> These files contain complex logic hidden in P2. You MUST request them before proposing changes."
    )
    lines.append(
        "> **Do NOT guess implementation details, error types, or edge case handling.**"
    )
    lines.append("")
    lines.append("| File | Hidden Complexity | Request Trigger |")
    lines.append("|------|-----------------|---------------|")
    for path, hint in KNOWN_UNKNOWNS:
        group = get_file_group(path)
        trigger = "Any change to this component or its consumers"
        if "test" in path:
            trigger = "Before modifying tested component"
        lines.append(f"| `{path}` | {hint} | {trigger} |")
    lines.append("")

    # 9. Request Protocol
    lines.append("---")
    lines.append("")
    lines.append("## 🚨 OBLIGATORY REQUEST PROTOCOL")
    lines.append("")
    lines.append("You MUST NOT guess implementation details. If you need to:")
    lines.append("- Verify error handling, retry logic, or edge cases")
    lines.append("- See actual HTTP call construction, JSON parsing, or SSE handling")
    lines.append("- Check database schema, SQL queries, or migration logic")
    lines.append("- Review test assertions before proposing changes")
    lines.append("- Copy-paste or refactor existing code")
    lines.append("- Understand any file marked with 🔒 or listed in Known Unknowns")
    lines.append("")
    lines.append("Then output **EXACTLY**:")
    lines.append("")
    lines.append("```")
    lines.append("🔍 REQUEST CODE: `relative/path/to/file.py`")
    lines.append("Reason: [1-sentence justification]")
    lines.append("```")
    lines.append("")
    lines.append(
        "**Forbidden:** Inventing method bodies, assuming exception types, hallucinating config keys, or guessing retry strategies. When in doubt — REQUEST."
    )
    lines.append("")
    lines.append("### Priority Rules for Compact Mode")
    lines.append(
        "1. **Always check P0/P1 first** — the public API is usually enough for architecture discussions."
    )
    lines.append("2. **Request code when:**")
    lines.append("   - You need to see implementation logic (not just interface)")
    lines.append("   - You need to verify how an adapter handles edge cases")
    lines.append("   - You need to copy-paste or refactor existing code")
    lines.append("   - The file is in Known Unknowns or marked with 🔒")
    lines.append(
        "3. **Batch requests** — ask for multiple files in one block if needed"
    )
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    # ── Auto-update ERROR_TAXONOMY.md before building context ──
    try:
        script_dir = Path(__file__).resolve().parent
        taxonomy_script = script_dir / "error_taxonomy_build.py"
        if taxonomy_script.exists():
            import subprocess

            result = subprocess.run(
                [sys.executable, str(taxonomy_script)],
                capture_output=True,
                text=True,
                cwd=find_project_root(),
            )
            if result.returncode == 0:
                print("[context_build] ERROR_TAXONOMY.md auto-updated")
            else:
                print(
                    f"[context_build] WARNING: taxonomy update failed: {result.stderr}",
                    file=sys.stderr,
                )
        else:
            print(
                "[context_build] NOTE: error_taxonomy_build.py not found, skipping auto-update",
                file=sys.stderr,
            )
    except Exception as exc:
        print(
            f"[context_build] WARNING: Could not auto-update taxonomy: {exc}",
            file=sys.stderr,
        )
    # ── End auto-update ──

    parser = argparse.ArgumentParser(
        description="Build AI context document for the project."
    )
    parser.add_argument(
        "--mode",
        choices=["compact", "full"],
        default="compact",
        help="compact: critical + signatures + inventory. full: everything.",
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
        "--output",
        type=str,
        default=None,
        help="Output filename relative to project root. Defaults to context_build_<mode>.md",
    )
    args = parser.parse_args()

    root = find_project_root()
    print(f"[context_build] Project root: {root}")

    # Sanity check: ensure we are not inside dev/ itself
    if root.name == "dev" and (root.parent / "README.md").exists():
        print(
            "[context_build] WARNING: Detected dev/ as root. Using parent instead.",
            file=sys.stderr,
        )
        root = root.parent

    print(f"[context_build] Mode: {args.mode}")

    critical, signature, other, metrics = scan_project(root, args.mode)

    print(f"[context_build] Metrics: {metrics}")
    print(f"[context_build] P0 critical files: {len(critical)}")
    print(f"[context_build] P1 signature files: {len(signature)}")
    print(f"[context_build] P2/other files: {len(other)}")

    # Auto-fallback if full context is too large
    if args.mode == "full" and metrics["py_loc"] > 16000:
        print(
            "[context_build] WARNING: Context too large. Accuracy may drop. Use compact mode."
        )
        print(f"[context_build] Python LOC: {metrics['py_loc']:,} > 16,000 limit.")
        print("[context_build] Auto-falling back to compact mode.")
        args.mode = "compact"

    out_name = args.output or DEFAULT_OUTPUT[args.mode]
    md = build_markdown(root, args.mode, critical, signature, other, metrics)

    # Save to dev/
    dev_dir = root / "dev"
    dev_dir.mkdir(parents=True, exist_ok=True)
    out_path = dev_dir / out_name

    out_path.write_text(md, encoding="utf-8")

    # Print relative path for readability
    rel_out = out_path.relative_to(root)
    print(f"[context_build] Written: {rel_out} ({len(md):,} chars)")


if __name__ == "__main__":
    main()
