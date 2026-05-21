#!/usr/bin/env python3
"""Context Builder — Full project context for AI analysis.
Generates context_build.md with architecture rules, file tree, and full source \
code.
Features: token-based limits, task-aware prioritization, critical decorator \
preservation.

Default mode: compact (48k tokens, excludes tests/ and scripts/).
Use --full for complete context (128k tokens, includes all files).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# ── Project Identity ──
PROJECT_NAME = "AI Assistant"
PROJECT_TAGLINE = (
    "A modular, cross-platform framework for local LLMs — 10+ years of evolution"
)

PROJECT_RULES = """
# AI Assistant — Модульный фреймворк для локальных LLM
-------------------------------------------------------------------------------

## ПРАВИЛА (СВЯЩЕННОЕ ЯДРО — НЕ ТРОГАТЬ)
- core/ports/, core/pipeline.py, core/registry.py, api/router.py — НЕИЗМЕНЯЕМЫ
- Новый адаптер: adapters/<port>_<name>.py + @register("<port>", "<name>")
- Новая фича: features/<name>/{handlers,manager,schemas}.py
- Новый шаг pipeline: @step("name") в pipeline/steps.py
- Новый промпт: core/prompts/v2/name.j2 (v1/ не трогать)
-------------------------------------------------------------------------------

## Слои
- core/ 🔒 Ядро: порты, домен, pipeline, registry, prompts/v1/*.j2
- adapters/ 🔌 Plug-and-play: llm_*, embedder_*, vector_store_*, memory_sqlite.py, tools_*.py
- features/ 📦 Изолированные: chat/, rag/, image_analysis(заглушка), voice_chat(заглушка)

-------------------------------------------------------------------------------

## Вспомогательное:
- pipeline/ 🔄 steps.py: embed_query→retrieve→rerank→build_context→generate
- api/ 🌐 lifespan.py, deps.py, router.py
- tests/ 🧪 233 pytest-теста, check_mutations.py

-------------------------------------------------------------------------------

## КОНФИГ (config.yaml + pyproject.toml — единый источник правды)
- llm.provider: openai_compatible | mock
- embedder.dim ДОЛЖЕН совпадать с vector_store.dim (по умолчанию: 768)
- rag.steps: [embed_query,retrieve,rerank,build_context,generate]
- rag.namespaces: personal/work/other → префиксы [p]/[w]/[o] в чате

-------------------------------------------------------------------------------

## БЫСТРЫЙ СТАРТ

```bash
# 1. Подготовь LLM-сервер с OpenAI-compatible API
#    Варианты:
#    • llama-server:  llama-server.exe -m model.gguf --port 8080
#    • Ollama:        ollama serve  (порт 11434)
#    • vLLM:          python -m vllm.entrypoints.openai.api_server --model ...
#    • OpenAI:        https://api.openai.com/v1 (api_key нужен)

# 2. Пропиши endpoint в config.yaml:
#    llm:
#      provider: openai_compatible
#      api_base: http://127.0.0.1:8080/v1   # или 11434 для Ollama
#      model: gemma-3-4b-it-Q4_K_M          # имя модели на сервере

# 3. Установи зависимости проекта
pip install -e .[dev]

# 4. Запусти сервер
python main.py
# или через uvicorn напрямую:
# uvicorn main:app --host 0.0.0.0 --port 8000

# 5. UI: браузерное расширение с OpenAI-compatible API → http://localhost:8000
```

## Рекомендуемые модели
- **LLM:** `gemma-3-4b-it`, `qwen2.5-7b-instruct`, `llama-3.2-3b-instruct` — быстрые, качественные, мультиязычные
- **Embedder:** `nomic-embed-text-v1.5`, `mxbai-embed-large-v1` — проверь размерность выходного вектора!

> 💡 Совет: убедись, что модель загружена в память/VRAM перед первым запросом, иначе первый ответ будет медленным.

-------------------------------------------------------------------------------

## RAG
- Индексация: `python scripts/index_documents.py --folder <personal|work|other>`
- Префикс в чате: `[p] запрос` — ищет только в personal namespace
- API переиндексации: POST /rag/reindex {folder, clear}

-------------------------------------------------------------------------------

## ВОРОТА КАЧЕСТВА (ОБЯЗАТЕЛЬНЫ ДЛЯ ЛЮБЫХ ИЗМЕНЕНИЙ)
```bash
pytest tests -v                           # 233 теста + hypothesis fuzz
python scripts/check_mutations.py --quick # mutmut, score >= 80% (core/)
python scripts/check_mutations.py         # mutmut, score >= 80% (полный)
python scripts/check_ruff.py --check      # lint чисто
python scripts/check_mypy.py              # типы чисто
```

-------------------------------------------------------------------------------

## ЧЕК-ЛИСТ ИНТЕГРАЦИИ AI (когда просишь помощи)
1. Прикрепи: context_build.md (из `python scripts/context_build.py --compact`)
2. Формат задачи: "Исправить/Добавить [X] в [файл/путь]"
3. Ограничения: Python 3.13+, Sacred Core неизменяем, offline-first
4. Прикрепи примеры: существующий адаптер/фича для справки
5. Требуй: pytest + mutation + ruff/mypy чисто в ответе
6. Проверь перед мержем: все ворота выше пройдены
-------------------------------------------------------------------------------

## ФОРМАТ ОТВЕТА ДЛЯ AI (строго)
- Отвечай ТОЛЬКО: code diff / путь к файлу / точная команда
- БЕЗ объяснений, БЕЗ markdown-ограждений, кроме показа кода
- Если не уверен: запроси конкретный файл/строку, не гадай
- Всегда уважай границы Sacred Core
-------------------------------------------------------------------------------

## ТРАБЛШУТИНГ
- LLM не отвечает → проверь, что сервер запущен и `AI_LLM_API_BASE` / `config.yaml → llm.api_base` указывают на правильный порт
- 401 Unauthorized → в config.yaml пропиши `api_key: sk-...` (если сервер требует ключ; локальные серверы обычно игнорируют любую строку)
- FAISS не ставится → vector_store.provider: memory в config.yaml
- Индекс не грузится → проверь права на data/indices/ и index_path в конфиге
- Несовпадение dim → embedder.dim и vector_store.dim должны быть равны (смотри спецификацию модели эмбеддеров)
- Не хватает зависимостей → `pip install -e .[dev]` из корня проекта
-------------------------------------------------------------------------------

## ЛИЦЕНЗИЯ: MIT
-------------------------------------------------------------------------------

# Frozen Invariants (не менять без обсуждения)

- `api/deps.py`: `_state` инициализируется ровно один раз через `asyncio.Event`
- `api/lifespan.py`: shutdown таргетит только PID, никогда process group
- `core/ports/`, `core/registry.py`, `core/pipeline.py`: immutable
- `features/*/`: новые фичи только через новые директории, существующие handlers не трогать
"""

RUNTIME_INFO = """
## [PKG] Runtime & Excluded Info
- **Environment:** `.venv/` — dependencies, excluded from context
- **Data:** `data/`, `documents/`, `logs/` — runtime files, excluded
- **Indices:** `data/indices/`, `*.faiss`, `*.db` — binaries/databases, excluded
- **Test cache:** `.hypothesis/` — property-based testing artifacts, excluded
- **Tasks:** `TODO.txt` — dev planner/checklist, excluded (external context)
"""
DEFAULT_EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "env",
    "ENV",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".github",
    ".vscode",
    ".idea",
    "node_modules",
    "dist",
    "build",
    "target",
    "data",
    "logs",
    "tmp",
    "temp",
    ".tox",
    ".eggs",
    "htmlcov",
    "documents",
    ".hypothesis",  # hypothesis fuzzing cache
}
DEFAULT_EXCLUDED_FILES = {
    "context_build.md",
    "context_build.py",  # self-reference excluded
    "todo.txt",
    "TODO.txt",  # development task tracker
    "structure.txt",
    ".env",
    ".env.local",
    ".gitignore",
    ".gitattributes",
    ".coverage",
    "coverage.xml",
    "setup.log",
    "test_errors.txt",
    "smoke_report.json",
}
EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".webp",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".mkv",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".faiss",
}
DEFAULT_MAX_TOKENS = 128_000
COMPACT_MAX_TOKENS = 48_000


def _ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows to prevent codec errors."""
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def load_contextignore(root: Path) -> tuple[set[str], set[str]]:
    extra_dirs, extra_files = set(), set()
    ignore = root / ".contextignore"
    if ignore.exists():
        for line in ignore.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            (extra_dirs if line.endswith("/") else extra_files).add(line.rstrip("/"))
    return extra_dirs, extra_files


def should_exclude(
    p: Path, root: Path, extra_dirs: set[str], extra_files: set[str]
) -> bool:
    for part in p.relative_to(root).parts:
        if (
            part in DEFAULT_EXCLUDED_DIRS
            or part in extra_dirs
            or part.endswith(".egg-info")
        ):
            return True
    name = p.name
    return (
        name in DEFAULT_EXCLUDED_FILES
        or name in extra_files
        or any(name.endswith(ext) for ext in EXCLUDED_EXTENSIONS)
    )


def is_text_file(p: Path) -> bool:
    try:
        return b"\0" not in p.read_bytes()[:8192]
    except Exception:
        return False


def format_size(s: int) -> str:
    return (
        f"{s} B"
        if s < 1024
        else f"{s / 1024:.1f} KB"
        if s < 1024**2
        else f"{s / (1024**2):.1f} MB"
    )


def get_language(p: Path) -> str:
    return {
        "py": "python",
        "md": "markdown",
        "yaml": "yaml",
        "yml": "yaml",
        "toml": "toml",
        "json": "json",
        "txt": "text",
        "sh": "bash",
        "bat": "batch",
        "j2": "jinja2",
        "cfg": "ini",
        "ini": "ini",
    }.get(p.suffix.lower(), p.suffix[1:] or "text")


def clean_content(text: str) -> str:
    # Reduce multiple blank lines to at most two (preserves readability)
    return re.sub(r"(?:\r?\n){3,}", "\n\n", text).strip()


def estimate_tokens(text: str) -> int:
    # Improved token approximation (~0.25 tokens per character for typical code)
    return max(1, int(len(text) * 0.25))


def has_critical_decorators(text: str) -> bool:
    return bool(re.search(r"@(register|step|router\.[a-z_]+|app\.[a-z_]+)\s*\(", text))


def get_task_priority(task: str | None, rel_path: str) -> int:
    if not task:
        return 1
    task_low = task.lower()
    if any(x in rel_path for x in ["registry.py", "pipeline.py", "ports/", "api/"]):
        return 0
    if "llm" in task_low and "llm_" in rel_path:
        return 0
    if "adapter" in task_low and "adapters/" in rel_path:
        return 0
    if "rag" in task_low and any(x in rel_path for x in ["rag/", "retrieve", "embed"]):
        return 0
    if "feature" in task_low and "features/" in rel_path:
        return 0
    return 2 if rel_path.startswith(("core/", "api/")) else 3


def build_architecture_summary(root: Path, files: list[Path]) -> str:
    has_core = any("core/ports" in f.relative_to(root).as_posix() for f in files)
    has_adapters = any("adapters/" in f.relative_to(root).as_posix() for f in files)
    has_features = any("features/" in f.relative_to(root).as_posix() for f in files)
    return (
        "## Architecture Summary\n"
        f"- **Core:** {'Sacred/Immutable' if has_core else 'Missing'}\n"
        f"- **Adapters:** {'Plug-and-play' if has_adapters else 'Missing'}\n"
        f"- **Features:** {'Isolated' if has_features else 'Missing'}\n"
    )


def build_overview(root: Path, files: list[Path]) -> list[str]:
    lines = ["## Runtime Context", ""]
    lines.append(f"- **Python:** {sys.version_info.major}.{sys.version_info.minor}+")
    for name, cond in [
        ("Entry points", lambda f: f.name in ("main.py", "run.py", "launcher.py")),
        ("Configuration", lambda f: f.name in ("config.yaml", "pyproject.toml")),
    ]:
        lst = [f.relative_to(root).as_posix() for f in files if cond(f)]
        if lst:
            lines.append(f"- **{name}:** {', '.join(f'`{x}`' for x in lst)}")
    lines.extend(["", "---", ""])
    return lines


def build_tree(files: list[Path], root: Path) -> str:
    tree: dict[str, dict[str, object]] = {}
    out = ["```"]
    for f in files:
        node = tree
        for part in f.relative_to(root).parts:
            node = node.setdefault(part, {})  # type: ignore[assignment]

    def render(node: dict[str, dict[str, object]], prefix: str = "") -> list[str]:
        items = sorted(node)
        result: list[str] = []
        for i, name in enumerate(items):
            is_last = i == len(items) - 1
            result.append(f"{prefix}{'└── ' if is_last else '├── '}{name}")
            result.extend(render(node[name], prefix + ("    " if is_last else "│   ")))
        return result

    out.extend(render(tree))
    out.append("```")
    return "\n".join(out)


def safe_read_text(p: Path) -> str:
    """Read text file with error handling for permission/encoding issues."""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (PermissionError, OSError) as e:
        print(f"[WARN] Skipping {p}: {e}", file=sys.stderr)
        return ""


def build_context(
    root: Path,
    out_path: Path,
    max_tokens: int,
    extra_dirs: set[str],
    extra_files: set[str],
    task: str | None,
    compact_mode: bool = False,  # noqa: ARG001
) -> None:
    # Prevent output file from being scanned as input
    if out_path.exists():
        try:
            if out_path.is_relative_to(root):
                extra_files.add(out_path.name)
        except ValueError:
            # out_path is not under root, ignore
            pass

    all_files = []
    for p in root.rglob("*"):
        if (
            p.is_file()
            and not p.is_symlink()
            and not should_exclude(p, root, extra_dirs, extra_files)
        ):
            if is_text_file(p):
                all_files.append(p)

    priorities = {
        f: get_task_priority(task, f.relative_to(root).as_posix()) for f in all_files
    }
    all_files.sort(key=lambda f: (priorities[f], f.relative_to(root).as_posix()))

    # Read contents safely
    contents: dict[Path, str] = {}
    for f in all_files:
        text = safe_read_text(f)
        if text:  # only include if read succeeded
            contents[f] = text

    # Filter out files that failed to read
    all_files = [f for f in all_files if f in contents]

    header = [
        "# Project Context",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Project:** {root.name}",
        f"**Files:** {len(all_files)}",
        "---",
        "",
    ]

    mini_readme = [
        f"# {PROJECT_NAME} — {PROJECT_TAGLINE}",
        "",
        PROJECT_RULES.strip(),
        "",
        "---",
        "",
        RUNTIME_INFO.strip(),
        "",
    ]
    arch = build_architecture_summary(root, all_files)
    overview = build_overview(root, all_files)
    tree_section = f"\n## Directory Structure\n{build_tree(all_files, root)}\n---\n"

    index = ["## File Index", ""]
    for i, f in enumerate(all_files, 1):
        rel = f.relative_to(root).as_posix()
        c = contents[f]
        lines = c.count("\n") + (1 if c and not c.endswith("\n") else 0)
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        idx_line = (
            f"{i}. `{rel}` — {format_size(f.stat().st_size)}, {lines} lines · {mtime}"
        )
        if has_critical_decorators(c):
            idx_line += " [CRIT]"
        index.append(idx_line)

    total_sz = sum(f.stat().st_size for f in all_files)
    index.extend(["", f"**Total:** {format_size(total_sz)}", "", "---", ""])

    content_out = ["## File Contents", ""]
    included, omitted, cur_tokens = [], [], 0
    for f in all_files:
        c = clean_content(contents[f])
        rel = f.relative_to(root).as_posix()
        lang = get_language(f)
        file_tokens = estimate_tokens(c)
        overhead_tokens = estimate_tokens(f"#### `{rel}`\n\n```{lang}\n\n```\n")
        total_file_tokens = file_tokens + overhead_tokens

        is_critical = has_critical_decorators(c) or (task and priorities[f] == 0)
        limit = max_tokens if not is_critical else int(max_tokens * 1.05)

        if cur_tokens + total_file_tokens <= limit:
            cur_tokens += total_file_tokens
            included.append(f)
        else:
            omitted.append(rel)

    if included:
        grouped: dict[str, list[Path]] = {}
        for f in included:
            parent = f.parent.relative_to(root).as_posix()
            grouped.setdefault(parent, []).append(f)
        for parent, files_in in sorted(grouped.items()):
            content_out.append(f"### `{parent}/`\n")
            for f in files_in:
                rel = f.relative_to(root).as_posix()
                lang = get_language(f)
                c = clean_content(contents[f])
                content_out.extend([f"#### `{rel}`", "", f"```{lang}", c, "```\n"])

    if omitted:
        content_out.extend(
            [
                "",
                f"> [WARN] **Token limit reached. Omitted {len(omitted)} files:**",
                "> "
                + ", ".join(f"`{p}`" for p in omitted[:20])
                + (" ..." if len(omitted) > 20 else ""),
                "",
            ]
        )

    parts = [
        "\n".join(header),
        "\n".join(mini_readme),
        arch,
        "\n".join(overview),
        tree_section,
        "\n".join(index),
        "\n".join(content_out),
    ]
    final_text = "\n".join(p.strip() for p in parts if p.strip()) + "\n"

    # Safety check for corrupted output
    if out_path.exists():
        existing_size = out_path.stat().st_size
        if existing_size > len(final_text) * 2:
            print(f"[WARN] Output file is unusually large ({existing_size} bytes)")
            print(f"   Expected ~{len(final_text)} bytes. Truncating.")

    out_path.write_text(final_text, encoding="utf-8")

    print(f"[OK] Wrote {out_path}")
    print(
        f"[FILES] {len(all_files)} total, {len(included)} included, "
        f"{len(omitted)} omitted"
    )
    print(f"[TOKENS] ~{cur_tokens} / {max_tokens}")


def main() -> None:
    _ensure_utf8_stdio()

    p = argparse.ArgumentParser(
        description="Build full AI context file. Default is compact mode "
        "(48k tokens, excludes tests/ and scripts/)."
    )
    p.add_argument("--output", "-o", default="context_build.md")
    p.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Soft token limit (overrides default based on mode)",
    )
    p.add_argument("--task", type=str, help="Task description for smart prioritization")
    p.add_argument("--exclude-dir", "-d", action="append", default=[])
    p.add_argument("--exclude-file", "-F", action="append", default=[])
    p.add_argument(
        "--full",
        action="store_true",
        help="Generate full context (128k tokens, includes all directories). "
        "Default is compact.",
    )
    # Deprecated: kept for backward compatibility but does nothing (compact is default)
    p.add_argument(
        "--compact",
        action="store_true",
        help=argparse.SUPPRESS,  # hidden, no-op
    )
    args = p.parse_args()

    root = Path(__file__).parent.parent.resolve()
    extra_dirs, extra_files = load_contextignore(root)
    extra_dirs.update(args.exclude_dir)
    extra_files.update(args.exclude_file)

    # Determine mode: full vs compact (default compact)
    if args.full:
        max_tokens = args.max_tokens if args.max_tokens else DEFAULT_MAX_TOKENS
        # No extra exclusions
    else:
        # Compact mode: exclude tests/ and scripts/, lower token limit
        extra_dirs.update({"tests", "scripts"})
        max_tokens = args.max_tokens if args.max_tokens else COMPACT_MAX_TOKENS

    build_context(
        root,
        root / args.output,
        max_tokens,
        extra_dirs,
        extra_files,
        args.task,
        compact_mode=not args.full,
    )


if __name__ == "__main__":
    sys.exit(main())
