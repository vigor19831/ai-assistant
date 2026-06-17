#!/usr/bin/env python3
"""
context_build.py — AI Context Builder.

Правила обработки папок:
  .venv .git data sources vendor — всегда исключены полностью
  docs — исключена, но ai_rules.md и error_taxonomy.md встроены в контекст
  scripts tests — список файлов в rules/compact, полное содержимое в full
"""

import argparse
import ast
import fnmatch
import logging
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("context_build")


# ============================================================================
# НАСТРОЙКИ
# ============================================================================

# ВСЕГДА исключены — не сканируем, не показываем
HARD_EXCLUDED = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", ".env", "node_modules", ".idea", ".vscode",
    "dist", "build", "*.egg-info",
    "data", "sources", "vendor",
    ".test_tmp", ".hypothesis",
}

# Сканируем, но обработка зависит от режима
SPECIAL_DIRS = {"docs", "scripts", "tests"}

# Файлы из docs, которые ВСЕГДА встроены в контекст (ищем в корне и в docs/)
REQUIRED_DOCS = ["ai_rules.md", "error_taxonomy.md", "DRIFT.md", "FUTURE.md"]

# Файлы, которые ВСЕГДА полностью в compact (кроме tests/scripts)
ALWAYS_FULL = {
    "config.yaml", "pyproject.toml", ".gitignore", "README.md",
}

# Пропускаем
SKIP_FILES = [
    "*.pyc", "*.pyo", "*.so", "*.dll", "*.exe",
    "*.gguf", "*.bin", "*.pt", "*.pth", "*.onnx", "*.safetensors",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp",
    "*.mp3", "*.wav", "*.lock", ".DS_Store", "Thumbs.db",
    "*.log", "*.pid",
    "structure.txt",
    "*context_build_*.md",
    "*.test.yaml", "*.test.yml",
    # Runtime scripts — not part of project code
    "run.py", "launcher.py",
    ".gitattributes", ".coverage",
]


# ============================================================================
# HELPERS
# ============================================================================

def find_project_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, *script_dir.parents]:
        if (parent / "README.md").exists() and (parent / "pyproject.toml").exists():
            return parent
    return script_dir.parent


def should_skip(rel_path: str) -> bool:
    basename = os.path.basename(rel_path)
    for pat in SKIP_FILES:
        if fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(rel_path, pat):
            return True
    return False


def count_loc(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def extract_imports(source: str) -> tuple[list[str], list[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []
    internal, external = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("ai_assistant"):
                names = ", ".join(a.name for a in node.names)
                internal.append(f"{mod}: {names}")
            elif not mod.startswith("."):
                external.append(mod.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                (internal if name == "ai_assistant" else external).append(name)
    return sorted(set(internal)), sorted(set(external))


# ============================================================================
# ERROR TAXONOMY BUILD
# ============================================================================

def _run_error_taxonomy(root: Path) -> None:
    """Generate error_taxonomy.md before building context.

    Runs error_taxonomy_build.py as a subprocess to ensure fresh data.
    """
    taxonomy_script = root / "scripts" / "error_taxonomy_build.py"
    if not taxonomy_script.exists():
        logger.warning("error_taxonomy_build.py not found, skipping")
        return

    try:
        result = subprocess.run(
            [sys.executable, str(taxonomy_script)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30.0,
        )
        if result.returncode == 0:
            logger.info("ERROR_TAXONOMY.md regenerated")
        else:
            logger.warning("error_taxonomy_build.py failed: %s", result.stderr[:200])
    except subprocess.TimeoutExpired:
        logger.warning("error_taxonomy_build.py timed out")
    except Exception as exc:
        logger.warning("error_taxonomy_build.py error: %s", exc)


# ============================================================================
# SCAN
# ============================================================================

def scan(root: Path, mode: str):
    """Сканируем файлы с учётом режима."""
    all_files = []      # (rel_path, content, size, type)
    py_files = []       # для графа зависимостей
    metrics = {"total": 0, "py": 0, "loc": 0, "classes": 0, "funcs": 0}

    for dirpath, dirnames, filenames in os.walk(root):
        # Исключаем жёстко
        dirnames[:] = [d for d in dirnames if d not in HARD_EXCLUDED]

        rel_dir = Path(dirpath).relative_to(root)
        parts = rel_dir.parts

        # Определяем тип папки
        is_docs = "docs" in parts
        is_scripts = "scripts" in parts
        is_tests = "tests" in parts
        is_special = is_docs or is_scripts or is_tests

        for fname in sorted(filenames):
            path = Path(dirpath) / fname
            rel = path.relative_to(root).as_posix()

            if should_skip(rel):
                continue

            size = path.stat().st_size
            metrics["total"] += 1

            # docs — не читаем содержимое (кроме REQUIRED_DOCS, но они отдельно)
            if is_docs:
                continue  # пропускаем, REQUIRED_DOCS добавим позже

            # Читаем содержимое
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            is_py = rel.endswith(".py")
            basename = os.path.basename(rel)

            if is_py:
                metrics["py"] += 1
                metrics["loc"] += count_loc(content)
                py_files.append((rel, content))
                try:
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            metrics["classes"] += 1
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            metrics["funcs"] += 1
                except SyntaxError:
                    pass

            # Определяем тип отображения
            if mode == "rules":
                all_files.append((rel, None, size, "listed"))

            elif mode == "full":
                # В full: scripts и tests полностью, остальные тоже полностью
                all_files.append((rel, content, size, "full"))

            else:  # compact
                if is_scripts or is_tests:
                    # Только список
                    all_files.append((rel, None, size, "listed"))
                elif basename in ALWAYS_FULL or "core" in parts or "api" in parts or "handlers" in basename or "schemas" in basename:
                    all_files.append((rel, content, size, "full"))
                elif is_py:
                    all_files.append((rel, content, size, "signature"))
                else:
                    all_files.append((rel, content, size, "listed"))

    # Добавляем REQUIRED_DOCS отдельно (ищем в корне и в docs/)
    for doc_name in REQUIRED_DOCS:
        found = False
        for location in [root / doc_name, root / "docs" / doc_name]:
            if location.exists():
                try:
                    content = location.read_text(encoding="utf-8", errors="replace")
                    all_files.append((doc_name, content, len(content), "doc"))
                    found = True
                    break
                except OSError:
                    continue
        if not found:
            logger.warning("Required doc not found: %s", doc_name)

    return all_files, py_files, metrics


# ============================================================================
# SIGNATURES
# ============================================================================

def extract_signature(source: str, rel_path: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"# Syntax error: {e}\n"

    lines = [f"# API: {rel_path}", ""]

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            try:
                lines.append(ast.unparse(node))
            except Exception:
                pass

        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
            sig = f"class {node.name}({bases}):" if bases else f"class {node.name}:"
            doc = ast.get_docstring(node)
            if doc:
                sig += f'''\n    """{doc[:200]}"""'''
            lines.append(sig)
            lines.append("")

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            try:
                args = ast.unparse(node.args)
            except Exception:
                args = "..."
            async_p = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            doc = ast.get_docstring(node)
            sig = f"{async_p}def {node.name}({args}):"
            if doc:
                sig += f'''\n    """{doc[:200]}"""'''
            lines.append(sig)
            lines.append("")

    return "\n".join(lines)


# ============================================================================
# BUILD MARKDOWN
# ============================================================================

def build_markdown(root: Path, mode: str, all_files, py_files, metrics):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Разделяем
    doc_files = [(r, c) for r, c, s, t in all_files if t == "doc"]
    full_files = [(r, c) for r, c, s, t in all_files if t == "full"]
    sig_files = [(r, c) for r, c, s, t in all_files if t == "signature"]
    listed_files = [(r, s) for r, c, s, t in all_files if t == "listed"]

    lines = [
        "# AI Context",
        f"> **Generated:** {now} | **Mode:** `{mode}`",
        f"> **Metrics:** {metrics['total']} files | {metrics['py']} Python | {metrics['loc']:,} LOC",
        f"> **Full:** {len(full_files)} | **Signatures:** {len(sig_files)} | **Listed:** {len(listed_files)}",
        "",
        "---",
        "",
    ]

    # README
    readme = root / "README.md"
    if readme.exists():
        lines.extend([
            "## 📋 Project Overview",
            "```markdown",
            readme.read_text(encoding="utf-8", errors="replace")[:2000],
            "```",
            "",
            "---",
            "",
        ])

    # AI Rules & Error Taxonomy (из doc_files)
    for rel, content in doc_files:
        title = "🚨 AI Development Guidelines" if "ai_rules" in rel else "⚠️ Error Taxonomy"
        lines.extend([
            f"## {title}",
            f"> Auto-extracted from: `{rel}`",
            "```markdown",
            content[:25000],
            "```",
            "",
            "---",
            "",
        ])

    # Structure
    lines.extend([
        "## 🗂️ Structure",
        "```",
    ])
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in HARD_EXCLUDED]
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts) - 1 if rel != Path(".") else 0
        if rel != Path("."):
            lines.append(f"{'    ' * depth}{rel.name}/")
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel_file = fpath.relative_to(root).as_posix()
            if not should_skip(rel_file):
                lines.append(f"{'    ' * (depth + 1)}{fname}")
    lines.extend(["```", "", "---", ""])

    # Dependencies
    if mode in ("rules", "compact") and py_files:
        lines.extend(["## 🔗 Dependencies", ""])
        graph = defaultdict(list)
        for rel, content in py_files:
            internal, _ = extract_imports(content)
            if internal:
                graph[rel] = internal
        for rel, imports in sorted(graph.items()):
            lines.append(f"- `{rel}`")
            for imp in imports:
                lines.append(f"  - → `{imp}`")
        lines.extend(["", "---", ""])

    # File Inventory
    lines.extend(["## 📦 Files", ""])
    if full_files:
        lines.append("### Full Content")
        for r, _ in sorted(full_files):
            lines.append(f"- `{r}`")
        lines.append("")
    if sig_files:
        lines.append("### Signatures Only")
        for r, _ in sorted(sig_files):
            lines.append(f"- `{r}`")
        lines.append("")
    if listed_files:
        lines.append("### Listed Only (no content)")
        for r, _ in sorted(listed_files):
            lines.append(f"- `{r}`")
        lines.append("")
    lines.extend(["---", ""])

    # Full Content
    if full_files:
        lines.extend(["## 🔑 Full Code", ""])
        for rel, content in sorted(full_files, key=lambda x: x[0]):
            ext = "python" if rel.endswith(".py") else "text"
            lines.extend([f"### `{rel}`", f"```{ext}", content, "```", ""])

    # Signatures
    if sig_files:
        lines.extend(["## 🧩 API Signatures", ""])
        for rel, content in sorted(sig_files, key=lambda x: x[0]):
            sig = extract_signature(content, rel)
            lines.extend([f"### `{rel}`", "```python", sig, "```", ""])

    return "\n".join(lines)


# ============================================================================
# WRITE
# ============================================================================

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


# ============================================================================
# MENU
# ============================================================================

def menu():
    print("\n  AI Context Builder")
    print("  ==================")

    options = [
        "rules  — структура, правила, зависимости (zero code)",
        "compact — критичные файлы + сигнатуры остальных",
        "full — ВСЁ полностью (включая тесты и скрипты)",
    ]

    print("\nВыберите режим:")
    for i, opt in enumerate(options, 1):
        marker = ">" if i == 2 else " "
        print(f"  {marker} [{i}] {opt}")

    while True:
        raw = input("\nВыбор [1-3], Enter = 2: ").strip()
        if raw == "":
            return "compact"
        if raw.isdigit() and 1 <= int(raw) <= 3:
            return ["rules", "compact", "full"][int(raw) - 1]
        print("Неверный ввод")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rules", "compact", "full"], default="rules")
    parser.add_argument("--output", default=None)

    root = find_project_root()

    script_parent = Path(__file__).resolve().parent
    if script_parent.name == "scripts" and script_parent.parent.exists():
        root = script_parent.parent

    if len(sys.argv) <= 1:
        mode = menu()
    else:
        mode = parser.parse_args().mode

    # ── Generate error taxonomy BEFORE scanning ──
    _run_error_taxonomy(root)

    all_files, py_files, metrics = scan(root, mode)

    logger.info("Total: %d | Python: %d | LOC: %d", metrics["total"], metrics["py"], metrics["loc"])

    md = build_markdown(root, mode, all_files, py_files, metrics)

    out_name = (len(sys.argv) > 1 and sys.argv[sys.argv.index("--output") + 1] if "--output" in sys.argv else None) or f"context_build_{mode}.md"
    out_path = root / out_name
    write_file(out_path, md)

    print(f"\nГотово: {out_path} ({len(md):,} символов, ~{len(md)//4:,} токенов)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
