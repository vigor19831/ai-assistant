"""Atomic file operations."""

from __future__ import annotations

import asyncio
import contextlib
import os
import stat
import tempfile
from pathlib import Path
from typing import cast

__all__ = ["atomic_write"]


async def atomic_write(
    path: str | Path,
    content: str | bytes,
    mode: str = "w",
) -> None:
    """Write *content* to *path* atomically via a temporary file.

    A sibling ``.tmp`` file is created in the same directory and moved
    into place with ``os.replace``.  On any failure the temporary file
    is removed.  The directory is fsync'd so the rename is durable.

    Preserves the permissions of an existing target file.  New files
    inherit the permissions from the temporary file (typically 0o600).
    """
    target = Path(path)

    if mode not in {"w", "wb"}:
        raise ValueError(f"mode must be 'w' or 'wb', got {mode!r}")

    binary = "b" in mode
    if binary and type(content) is not bytes:
        raise TypeError(
            f"Expected bytes for mode={mode!r}, got {type(content).__name__}"
        )
    if not binary and type(content) is not str:
        raise TypeError(f"Expected str for mode={mode!r}, got {type(content).__name__}")

    def _sync() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            if binary:
                with os.fdopen(fd, mode, closefd=True) as fh:
                    fh.write(cast("bytes", content))
                    fh.flush()
                    os.fsync(fh.fileno())
            else:
                with os.fdopen(fd, mode, closefd=True, encoding="utf-8") as fh:
                    fh.write(cast("str", content))
                    fh.flush()
                    os.fsync(fh.fileno())

            # Preserve permissions of existing target file.
            # mkstemp creates files with 0o600; os.replace swaps inodes,
            # so the new file would inherit 0o600.  Copy the old mode
            # to the temp file before the replace so it survives.
            if target.exists():
                old_mode = stat.S_IMODE(os.stat(target).st_mode)
                os.chmod(tmp, old_mode)

            os.replace(tmp, target)
            # Persist directory metadata (POSIX)
            try:
                dir_fd = os.open(
                    target.parent,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                )
            except OSError:
                pass  # Windows or filesystem without directory fsync support
            else:
                try:
                    os.fsync(dir_fd)
                except OSError:
                    pass  # filesystem does not support fsync on directories
                finally:
                    os.close(dir_fd)
        finally:
            # os.replace() already atomically removes tmp on success.
            # On failure (before replace), tmp may remain; mkstemp creates
            # files in the target dir, so we must clean up.
            with contextlib.suppress(OSError):
                os.unlink(tmp)

    await asyncio.to_thread(_sync)
