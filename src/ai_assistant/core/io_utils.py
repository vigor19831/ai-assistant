"""Atomic file operations."""

from __future__ import annotations

import asyncio
import contextlib
import os
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
    """
    target = Path(path)

    if mode not in {"w", "wb"}:
        raise ValueError(f"mode must be 'w' or 'wb', got {mode!r}")

    binary = "b" in mode
    if binary and not isinstance(content, bytes):
        raise TypeError(
            f"Expected bytes for mode={mode!r}, got {type(content).__name__}"
        )
    if not binary and not isinstance(content, str):
        raise TypeError(f"Expected str for mode={mode!r}, got {type(content).__name__}")

    def _sync() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, mode, closefd=True) as fh:
                if binary:
                    fh.write(cast("bytes", content))
                else:
                    fh.write(cast("str", content))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
            # Persist directory metadata (POSIX)
            if hasattr(os, "O_DIRECTORY"):
                dir_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp)

    await asyncio.to_thread(_sync)
