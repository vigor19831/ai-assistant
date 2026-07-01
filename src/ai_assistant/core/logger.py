"""Structured logging with text/json format support and trace_id propagation."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from typing import Final

__all__ = ["get_logger", "setup_logging"]

_LOCK: Final = threading.Lock()
_VALID_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)


class _TextFormatter(logging.Formatter):
    """Text formatter with trace_id support — thread-safe."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", None)
        trace_prefix = f"trace_id={trace_id} | " if trace_id else ""
        record.message = record.getMessage()
        record.asctime = self.formatTime(record, self.datefmt)
        return (
            f"{record.asctime} | {record.levelname:8} | {record.name} | "
            f"{trace_prefix}{record.message}"
        )


class _JsonFormatter(logging.Formatter):
    """JSON formatter with structured fields including trace_id.

    Extra fields are detected dynamically by comparing against a baseline
    LogRecord, so this does not hardcode Python version-specific attributes.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            log_entry["trace_id"] = trace_id

        # Detect extra fields by diffing against a default LogRecord.
        # This set is computed once per format call — cheap and future-proof.
        baseline = vars(logging.makeLogRecord({}))
        for key, value in record.__dict__.items():
            if key not in baseline and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = "./data/app.log",
    fmt: str = "text",
    max_bytes: int = 10_485_760,
    backup_count: int = 2,
) -> logging.Logger:
    """Configure application logging.

    When log_file is set, writes to file ONLY. Console output is
    captured by run_servers.py into server_8000.log; writing to
    both places duplicates every line. Use console-only when
    log_file is None (e.g. tests, docker).

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file, or None for console-only.
        fmt: Log format — "text" or "json".
        max_bytes: Maximum size in bytes before rotating the log file.
        backup_count: Number of backup files to keep.

    Repeated calls clear existing handlers and recreate them,
    allowing format changes at runtime (e.g., on config reload).
    """
    upper = level.upper()
    if upper not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}. Use one of: {sorted(_VALID_LEVELS)}"
        )

    if fmt not in {"text", "json"}:
        raise ValueError(f"Invalid log format {fmt!r}. Use 'text' or 'json'.")

    logger = logging.getLogger("ai_assistant")
    logger.setLevel(getattr(logging, upper))

    with _LOCK:
        # Clear existing handlers to allow format reconfiguration
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

        formatter: logging.Formatter = (
            _TextFormatter() if fmt == "text" else _JsonFormatter()
        )

        if log_file:
            # File only — console output is captured by run_servers.py
            # into server_8000.log, which duplicates app.log. Avoid double
            # logging by writing to file only when log_file is configured.
            pass  # file handler added below
        else:
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            logger.addHandler(console)

        if log_file:
            path = Path(log_file)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.handlers.RotatingFileHandler(
                    path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
                fh.setFormatter(formatter)
                logger.addHandler(fh)
            except OSError as exc:
                sys.stderr.write(f"Failed to create log file {path}: {exc}\n")

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get child logger."""
    return logging.getLogger(f"ai_assistant.{name}")
