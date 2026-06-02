#!/usr/bin/env python3
"""
Очистка проекта от кэша, временных файлов и артефактов сборки.

Использование:
    python scripts/clean_cache.py              # сухой прогон
    python scripts/clean_cache.py --clean      # реально удалить
"""

from __future__ import annotations

import argparse
import errno
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

# ── Конфигурация ──

# Удаляем всегда (безопасно)
SAFE_PATTERNS: list[str] = [
    "__pycache__",
    "*.py[cod]",
    "*$py.class",
    "*.egg-info",
    ".eggs",
    "*.egg",
    "build",
    "dist",
    ".pytest_cache",
    ".pytest-xdist",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".coverage",
    ".coverage.*",
    "htmlcov",
    ".tox",
    ".nox",
    ".dmypy",
    ".dmypy.json",
    ".ipynb_checkpoints",
    "*.log",
    "*.tmp",
    "*.bak",
    "*.orig",
    "pip-wheel-metadata",
]

# Не трогать никогда
NEVER_TOUCH: set[str] = {
    ".git",
    ".venv",
    "vendor",
    "config.yaml",
    "pyproject.toml",
    "README.md",
    "README_DEV.md",
    "AI_RULES.md",
}

# Системный Temp: только наши артефакты (pytest/tempfile)
SYSTEM_TEMP_PATTERNS: list[str] = ["tmp_*", "test.db", "pytest-*"]


# ── Логика ──


def _is_safe_to_delete(target: Path, root: Path) -> bool:
    """Check if target is safe to delete (not in NEVER_TOUCH, not .venv)."""
    try:
        rel_parts = target.relative_to(root).parts
    except ValueError:
        rel_parts = target.parts

    if any(part in NEVER_TOUCH for part in rel_parts):
        return False
    if ".venv" in rel_parts:
        return False
    return True


def find_targets(root: Path, patterns: list[str]) -> list[Path]:
    """Найти все пути в проекте, соответствующие паттернам."""
    targets: set[Path] = set()

    for pattern in patterns:
        for p in root.rglob(pattern):
            if not _is_safe_to_delete(p, root):
                continue
            targets.add(p.resolve())

    return sorted(targets)


def find_system_temp_targets() -> list[Path]:
    """Найти артефакты тестов в системном Temp (кроссплатформенно)."""
    temp_dir = Path(tempfile.gettempdir())
    targets: set[Path] = set()

    # Ищем tmp_* папки и pytest-* папки
    for pattern in SYSTEM_TEMP_PATTERNS:
        for p in temp_dir.glob(pattern):
            targets.add(p.resolve())

    # Ищем test.db внутри tmp_* папок (глубже первого уровня)
    for p in temp_dir.glob("tmp_*"):
        if p.is_dir():
            for db in p.rglob("test.db"):
                targets.add(db.resolve())
            # И любые другие .db артефакты тестов — только если имя содержит test
            for db in p.rglob("*.db"):
                if "test" in db.name.lower():
                    targets.add(db.resolve())

    return sorted(targets)


def format_size(path: Path | int) -> str:
    """Форматировать размер файла/директории или число байт."""
    if isinstance(path, int):
        size = float(path)
    elif isinstance(path, Path):
        if path.is_file():
            size = float(path.stat().st_size)
        elif path.is_dir():
            # Use os.walk to avoid symlink loops
            total = 0
            for dirpath, _dirnames, filenames in os.walk(path, topdown=True):
                for fname in filenames:
                    fpath = Path(dirpath) / fname
                    try:
                        total += fpath.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
            size = float(total)
        else:
            return "?"
    else:
        return "?"

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            if unit == "B" and size == int(size):
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def delete_target(path: Path) -> tuple[bool, bool]:
    """Удалить файл или директорию. Returns (success, is_locked)."""
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        return True, False
    except OSError as e:
        # Windows: файл занят другим процессом (сервер запущен)
        # Linux: EBUSY, EACCES, EPERM
        if e.errno in (errno.EACCES, errno.EPERM, errno.EBUSY):
            print(f"  [SKIP] {path}: locked by running process")
            return False, True
        if getattr(e, "winerror", None) == 32:
            print(f"  [SKIP] {path}: locked by running process")
            return False, True
        print(f"  [ERROR] {path}: {e}")
        return False, False
    except Exception as e:
        print(f"  [ERROR] {path}: {e}")
        return False, False


def print_section(title: str, targets: list[Path], root: Path | None = None) -> None:
    """Красивый вывод секции."""
    if not targets:
        return

    dirs = [t for t in targets if t.is_dir()]
    files = [t for t in targets if t.is_file()]

    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

    for d in dirs:
        rel = str(d.relative_to(root)) if root and d.is_relative_to(root) else str(d)
        print(f"  [DIR]  {rel:<50} {format_size(d):>10}")
    for f in files:
        rel = str(f.relative_to(root)) if root and f.is_relative_to(root) else str(f)
        print(f"  [FILE] {rel:<50} {format_size(f):>10}")

    total = sum(
        sum(x.stat().st_size for x in t.rglob("*") if x.is_file()) if t.is_dir() else t.stat().st_size
        for t in targets
    )
    print(f"{'─' * 60}")
    print(f"  Всего: {len(dirs)} директорий, {len(files)} файлов  ({format_size(total)})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean project cache and artifacts")
    parser.add_argument(
        "--clean", "-c", action="store_true", help="Actually delete (default: dry run)"
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )
    args = parser.parse_args()

    dev_root = Path(__file__).parent.parent.resolve()
    # Находим реальный корень проекта (где src/ai_assistant)
    if (dev_root / "src" / "ai_assistant").exists():
        root = dev_root
    elif (dev_root.parent / "src" / "ai_assistant").exists():
        root = dev_root.parent
    else:
        root = dev_root.parent  # fallback

    all_targets: list[Path] = []

    # ── 1. Проект ──
    project_targets = find_targets(root, SAFE_PATTERNS)
    if project_targets:
        print_section("Проект", project_targets, root)
        all_targets.extend(project_targets)

    # ── 2. Системный Temp (кроссплатформенно) ──
    system_targets = find_system_temp_targets()
    if system_targets:
        print_section(f"Системный Temp  ({tempfile.gettempdir()})", system_targets)
        all_targets.extend(system_targets)

    if not all_targets:
        print("Нечего удалять — всё чисто.")
        return 0

    if not args.clean:
        print(f"\n{'=' * 60}")
        print("Сухой прогон. Для удаления добавьте флаг --clean")
        print("Команда: python scripts/clean_cache.py --clean")
        return 0

    # Confirmation unless --yes
    if not args.yes:
        if not sys.stdin.isatty():
            print("Non-interactive mode detected. Use --yes to confirm deletion.")
            return 1
        try:
            ans = input("\nУдалить перечисленные файлы? [y/N]: ").strip().lower()
        except EOFError:
            print("Отменено.")
            return 1
        if ans not in ("y", "yes"):
            print("Отменено.")
            return 0

    print(f"\n{'=' * 60}")
    print("Удаление...")
    deleted = 0
    skipped = 0
    failed = 0
    for target in all_targets:
        ok, locked = delete_target(target)
        rel = str(target.relative_to(root)) if target.is_relative_to(root) else str(target)
        if ok:
            print(f"  [OK]   {rel}")
            deleted += 1
        elif locked:
            skipped += 1
        else:
            failed += 1

    print(f"{'=' * 60}")
    print(f"Удалено: {deleted}, пропущено (занято): {skipped}, ошибок: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
