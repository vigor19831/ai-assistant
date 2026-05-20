"""Atomic file operations."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path


async def atomic_write(path: str | Path, content: str | bytes, mode: str = "w") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        if "b" in mode:
            os.write(fd, content if isinstance(content, bytes) else content.encode())
        else:
            os.write(fd, content.encode() if isinstance(content, str) else content)
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if await asyncio.to_thread(os.path.exists, tmp):
            await asyncio.to_thread(os.unlink, tmp)
        raise
