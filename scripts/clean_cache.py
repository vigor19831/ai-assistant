#!/usr/bin/env python3
"""
Clean project cache, temporary files, and build artifacts.

Usage:
    python scripts/clean_cache.py
"""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import socket
import stat
import sys
from collections.abc import Callable
from pathlib import Path

# ── Configuration ──

SAFE_PATTERNS: list[str] = [
    "__pycache__",
    "*.py[cod]",
    "*$py.class",
    "*.so",
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
    ".test_tmp",
    ".pytest_tmp",
    ".mutmut-cache",
    "mutmut.xml",
]

# Besides the traversed dirs (.git/.venv/vendor match SAFE_PATTERNS
# from the inside), these also guard future pattern additions: a file
# entry is unreachable until a matching pattern ever appears.
NEVER_TOUCH: set[str] = {
    ".git",
    ".venv",
    "vendor",
    "config.yaml",
    "config.test.yaml",
    "pyproject.toml",
    "README.md",
    ".env",
}

# Stack ports: LLM 8080, embedder 8081, reranker 8082, API 8000.
# Mirrors PORTS in run_servers.py — edit both together.
_STACK_PORTS: tuple[int, ...] = (8080, 8081, 8082, 8000)


# ── Logic ──


def _is_safe_to_delete(target: Path, root: Path) -> bool:
    try:
        rel_parts = target.relative_to(root).parts
    except ValueError:
        rel_parts = target.parts
    return not any(part in NEVER_TOUCH for part in rel_parts)


def _stack_running() -> bool:
    """True when the AI stack is up (llama-server / uvicorn).

    Live-stack logs are skipped on deletion: on Linux an open file
    unlinks silently (the process writes into a deleted inode and
    the log never reappears until restart) — the Windows "locked"
    behavior must be explicit here, not OS-dependent.
    """
    for port in _STACK_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
    return False


def find_targets(root: Path, patterns: list[str]) -> list[Path]:
    targets: set[Path] = set()
    for pattern in patterns:
        for p in root.rglob(pattern):
            if not _is_safe_to_delete(p, root):
                continue
            targets.add(p.resolve())
    return sorted(targets)


def format_size(path: Path | int) -> str:
    if isinstance(path, int):
        size = float(path)
    elif isinstance(path, Path):
        try:
            if path.is_symlink():
                size = float(path.lstat().st_size)
            elif path.is_file():
                size = float(path.stat().st_size)
            elif path.is_dir():
                total = 0
                for dirpath, _dirnames, filenames in os.walk(path, topdown=True):
                    for fname in filenames:
                        fpath = Path(dirpath) / fname
                        with contextlib.suppress(OSError):
                            total += fpath.lstat().st_size
                size = float(total)
            else:
                return "?"
        except OSError:
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


def _rmtree_onerror(
    func: Callable[..., object], path: str, exc_info: tuple[object, object, object]
) -> None:
    """Pre-onexc error handler for shutil.rmtree (Python <= 3.11).

    Same contract as _rmtree_onexc below: read-only files on Windows
    are made writable and the failed operation is retried once.
    Kept until the project minimum moves past 3.11.
    """
    try:
        os.chmod(path, stat.S_IWUSR)
        func(path)
    except OSError:
        pass


def _rmtree_onexc(func: Callable[..., object], path: str, exc: BaseException) -> None:
    """onexc error handler for shutil.rmtree (Python >= 3.12).

    Handles read-only files on Windows by making them writable and
    retrying the failed operation once.
    """
    try:
        os.chmod(path, stat.S_IWUSR)
        func(path)
    except OSError:
        pass


def delete_target(path: Path) -> tuple[bool, str]:
    """
    Delete target. Returns (success, reason).
    reason is empty string on success.
    """
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            # onexc exists since Python 3.12; onerror is deprecated.
            # Until the project minimum passes 3.11, pick at runtime.
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=_rmtree_onexc)
            else:
                shutil.rmtree(path, onerror=_rmtree_onerror)
        return True, ""
    except OSError as e:
        if e.errno == errno.ENOENT:
            # Vanished between listing and deleting — success, not
            # an error (was counted as a failure).
            return True, ""
        if e.errno in (errno.EACCES, errno.EPERM, errno.EBUSY):
            return False, "locked by running process"
        if getattr(e, "winerror", None) == 32:
            return False, "locked by running process"
        return False, str(e)
    except Exception as e:
        return False, str(e)


def print_section(title: str, targets: list[Path], root: Path | None = None) -> None:
    if not targets:
        return
    dirs = [t for t in targets if t.is_dir()]
    files = [t for t in targets if t.is_file() or t.is_symlink()]
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")
    for d in dirs:
        rel = str(d.relative_to(root)) if root and d.is_relative_to(root) else str(d)
        print(f"  [DIR]  {rel:<50} {format_size(d):>10}")
    for f in files:
        rel = str(f.relative_to(root)) if root and f.is_relative_to(root) else str(f)
        print(f"  [FILE] {rel:<50} {format_size(f):>10}")
    # A file inside a listed directory is counted once via the dir
    # walk — the old loop double-counted such files.
    listed_dirs = {t for t in targets if t.is_dir()}
    total = 0
    for t in targets:
        try:
            if t.is_dir():
                total += sum(
                    x.lstat().st_size
                    for x in t.rglob("*")
                    if x.is_file() or x.is_symlink()
                )
            elif (t.is_file() or t.is_symlink()) and not any(
                p in listed_dirs for p in t.parents
            ):
                total += t.lstat().st_size
        except OSError:
            pass
    print(f"{'─' * 60}")
    print(f"  Total: {len(dirs)} dirs, {len(files)} files  ({format_size(total)})")


def _detect_project_root() -> Path:
    """Find project root by looking for pyproject.toml or .git."""
    current = Path(__file__).resolve().parent
    while current.parent != current:
        if (current / "pyproject.toml").exists() or (current / ".git").exists():
            return current
        current = current.parent
    print("ERROR: Could not detect project root.", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    root = _detect_project_root()

    # ── Menu ──
    print("Select action:")
    print("  [1] Delete cache")
    print("  [2] Show cache list only")

    try:
        ans = input("Choice [1]: ").strip()
    except EOFError:
        ans = "2"
    except KeyboardInterrupt:
        print("\nCancelled — nothing deleted.")
        return 0

    targets = find_targets(root, SAFE_PATTERNS)
    if not targets:
        print("Nothing to clean — everything is clean.")
        return 0

    print_section("Project", targets, root)

    if ans == "2":
        return 0

    # ans == "1" or default — delete
    print(f"\n{'=' * 60}")
    print("Deleting...")
    deleted = 0
    skipped = 0
    failed = 0
    stack_live = _stack_running()
    for target in targets:
        if stack_live and target.suffix == ".log":
            skipped += 1
            print(f"  [SKIP] {target.name} — live stack (restart or stop first)")
            continue
        ok, reason = delete_target(target)
        rel = (
            str(target.relative_to(root))
            if target.is_relative_to(root)
            else str(target)
        )
        if ok:
            print(f"  [OK]   {rel}")
            deleted += 1
        else:
            print(f"  [SKIP] {rel}: {reason}")
            if "locked" in reason:
                skipped += 1
            else:
                failed += 1

    print(f"{'=' * 60}")
    print(f"Deleted: {deleted}, skipped (locked): {skipped}, errors: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
