"""Simple structured logging."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Final

__all__ = ["get_logger", "setup_logging"]

_LOCK: Final = threading.Lock()
_VALID_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)


class _TraceFormatter(logging.Formatter):
    """Formatter that includes trace_id when present in extra."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            record.trace_id_str = f" | trace_id={trace_id}"
        else:
            record.trace_id_str = ""
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = "./data/app.log",
) -> logging.Logger:
    """Configure application logging.

    Idempotent: repeated calls reuse existing handlers but always
    refresh the logger level.
    """
    upper = level.upper()
    if upper not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}. Use one of: {sorted(_VALID_LEVELS)}"
        )

    logger = logging.getLogger("ai_assistant")
    logger.setLevel(getattr(logging, upper))

    with _LOCK:
        if logger.handlers:
            return logger

        fmt = "%(asctime)s | %(levelname)-8s | %(name)s%(trace_id_str)s | %(message)s"
        formatter = _TraceFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_file:
            path = Path(log_file)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(path, encoding="utf-8")
                fh.setFormatter(formatter)
                logger.addHandler(fh)
            except OSError as exc:
                logger.error("Failed to create log file %s: %s", path, exc)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get child logger."""
    return logging.getLogger(f"ai_assistant.{name}")
