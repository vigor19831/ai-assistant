#!/usr/bin/env python3
"""
Очистка проекта от кэша, временных файлов и артефактов сборки.

Использование:
    python scripts/clean_cache.py              # сухой прогон (показать что удалит)
    python scripts/clean_cache.py --clean      # реально удалить
"""

from __future__ import annotations

import argparse
import shutil
import sys
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
}


# ── Логика ──


def find_targets(root: Path, patterns: list[str]) -> list[Path]:
    """Найти все пути, соответствующие паттернам."""
    targets: set[Path] = set()

    for pattern in patterns:
        for p in root.rglob(pattern):
            if p.name in NEVER_TOUCH:
                continue
            # Защита: не лезть в .venv даже если __pycache__ там найден
            try:
                if ".venv" in p.relative_to(root).parts:
                    continue
            except ValueError:
                continue
            targets.add(p.resolve())

    return sorted(targets)


def format_size(path: Path | int) -> str:
    """Форматировать размер файла/директории или число байт."""
    if isinstance(path, int):
        size = float(path)
    elif isinstance(path, Path):
        if path.is_file():
            size = float(path.stat().st_size)
        elif path.is_dir():
            size = float(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()))
        else:
            return "?"
    else:
        return "?"

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            # Без десятичных для целых байт, с десятичными для остального
            if unit == "B" and size == int(size):
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def delete_target(path: Path) -> bool:
    """Удалить файл или директорию."""
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        return True
    except Exception as e:
        print(f"  [ERROR] {path}: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean project cache and artifacts")
    parser.add_argument(
        "--clean", "-c", action="store_true", help="Actually delete (default: dry run)"
    )
    args = parser.parse_args()

    root = Path(__file__).parent.parent.resolve()

    targets = find_targets(root, SAFE_PATTERNS)

    if not targets:
        print("Нечего удалять — проект чист.")
        return 0

    dirs = [t for t in targets if t.is_dir()]
    files = [t for t in targets if t.is_file()]

    print(f"Найдено для удаления: {len(dirs)} директорий, {len(files)} файлов")
    print("-" * 60)

    for d in dirs:
        rel_str = str(d.relative_to(root))
        print(f"  [DIR]  {rel_str:<50} {format_size(d):>10}")
    for f in files:
        rel_str = str(f.relative_to(root))
        print(f"  [FILE] {rel_str:<50} {format_size(f):>10}")
    print("-" * 60)

    if not args.clean:
        print("Сухой прогон. Для удаления добавьте флаг --clean")
        print("Команда: python scripts/clean_cache.py --clean")
        return 0

    print("Удаление...")
    deleted = 0
    failed = 0
    for target in targets:
        if delete_target(target):
            rel_str = str(target.relative_to(root))
            print(f"  [OK]   {rel_str}")
            deleted += 1
        else:
            failed += 1

    print("-" * 60)
    print(f"Удалено: {deleted}, ошибок: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
