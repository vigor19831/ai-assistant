"""Tests for core/logger.py — structured logging setup."""

from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from ai_assistant.core.logger import (
    _JsonFormatter,
    _TextFormatter,
    _VALID_LEVELS,
    get_logger,
    setup_logging,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeLogRecord:
    """Minimal LogRecord stand-in for formatter tests."""

    def __init__(
        self,
        name: str = "test",
        level: int = logging.INFO,
        msg: str = "hello",
        args: tuple[Any, ...] = (),
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.levelname = logging.getLevelName(level)
        self.levelno = level
        self.msg = msg
        self.args = args
        self.trace_id = extra.get("trace_id") if extra else None
        self.custom_field = extra.get("custom_field") if extra else None
        self.asctime = "2024-01-01 00:00:00,000"
        self.datefmt = None
        self.exc_info = None
        self.exc_text = None
        self.stack_info = None
        self.lineno = 1
        self.pathname = "test.py"
        self.filename = "test.py"
        self.module = "test"
        self.funcName = "test_func"
        self.created = 1704067200.0
        self.msecs = 0
        self.relativeCreated = 0.0
        self.thread = threading.current_thread().ident
        self.threadName = threading.current_thread().name
        self.processName = "MainProcess"
        self.process = 1

    def getMessage(self) -> str:
        return self.msg % self.args if self.args else self.msg


# ---------------------------------------------------------------------------
# _TextFormatter
# ---------------------------------------------------------------------------


def test_text_formatter_basic() -> None:
    """Text formatter produces expected line without trace_id."""
    fmt = _TextFormatter()
    record = _FakeLogRecord(msg="basic message")
    line = fmt.format(record)
    assert "INFO" in line
    assert "basic message" in line
    assert "trace_id=" not in line


def test_text_formatter_with_trace_id() -> None:
    """Text formatter includes trace_id when present."""
    fmt = _TextFormatter()
    record = _FakeLogRecord(msg="traced", extra={"trace_id": "abc123"})
    line = fmt.format(record)
    assert "trace_id=abc123" in line
    assert "traced" in line


# ---------------------------------------------------------------------------
# _JsonFormatter
# ---------------------------------------------------------------------------


def test_json_formatter_basic() -> None:
    """JSON formatter produces valid JSON with required fields."""
    fmt = _JsonFormatter()
    record = _FakeLogRecord(msg="json test")
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "json test"
    assert parsed["logger"] == "test"
    assert "timestamp" in parsed


def test_json_formatter_with_trace_id() -> None:
    """JSON formatter includes trace_id as top-level field."""
    fmt = _JsonFormatter()
    record = _FakeLogRecord(msg="traced", extra={"trace_id": "xyz789"})
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["trace_id"] == "xyz789"


def test_json_formatter_extra_fields() -> None:
    """JSON formatter captures custom extra fields."""
    fmt = _JsonFormatter()
    record = _FakeLogRecord(
        msg="extra",
        extra={"custom_field": "custom_value"},
    )
    line = fmt.format(record)
    parsed = json.loads(line)
    assert parsed["custom_field"] == "custom_value"


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_returns_logger(tmp_path: Path) -> None:
    """setup_logging returns the ai_assistant root logger."""
    log_file = tmp_path / "test.log"
    logger = setup_logging(level="DEBUG", log_file=str(log_file), fmt="text")
    assert logger.name == "ai_assistant"
    assert logger.level == logging.DEBUG


def test_setup_logging_invalid_level() -> None:
    """Invalid level raises ValueError."""
    with pytest.raises(ValueError, match="Invalid log level"):
        setup_logging(level="INVALID")


def test_setup_logging_invalid_format() -> None:
    """Invalid format raises ValueError."""
    with pytest.raises(ValueError, match="Invalid log format"):
        setup_logging(fmt="xml")


def test_setup_logging_reconfigure_clears_handlers(tmp_path: Path) -> None:
    """Repeated calls clear old handlers and apply new config."""
    log_file = tmp_path / "reconfig.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="text")
    first_handler_count = len(logger.handlers)

    logger2 = setup_logging(level="DEBUG", log_file=str(log_file), fmt="json")
    assert logger2 is logger  # same logger object
    assert len(logger.handlers) == first_handler_count  # same count, new instances
    assert logger.level == logging.DEBUG


def test_setup_logging_console_only() -> None:
    """log_file=None produces only console handler."""
    logger = setup_logging(level="INFO", log_file=None, fmt="text")
    assert all(
        not isinstance(h, logging.handlers.RotatingFileHandler)
        for h in logger.handlers
    )


def test_setup_logging_file_handler_created(tmp_path: Path) -> None:
    """log_file set creates RotatingFileHandler."""
    log_file = tmp_path / "file.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="text")
    file_handlers = [
        h for h in logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1


def test_setup_logging_file_write(tmp_path: Path) -> None:
    """Log messages are written to the file."""
    log_file = tmp_path / "write.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="text")
    logger.info("file test message")
    # Flush handlers
    for h in logger.handlers:
        h.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "file test message" in content


def test_setup_logging_json_format(tmp_path: Path) -> None:
    """JSON format writes parseable JSON lines."""
    log_file = tmp_path / "json.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="json")
    logger.info("json msg")
    for h in logger.handlers:
        h.flush()
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    parsed = json.loads(lines[0])
    assert parsed["message"] == "json msg"


def test_setup_logging_oserror_on_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError on file creation writes to stderr, does not crash."""
    def _raise(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", _raise)
    # Use a path that parent does not exist to trigger the error path
    log_file = tmp_path / "nonexistent" / "sub" / "test.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="text")
    assert logger.name == "ai_assistant"


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


def test_get_logger_returns_child() -> None:
    """get_logger returns a child of ai_assistant."""
    logger = get_logger("test_module")
    assert logger.name == "ai_assistant.test_module"


def test_get_logger_propagates_level() -> None:
    """Child logger inherits level from parent."""
    setup_logging(level="WARNING", log_file=None, fmt="text")
    child = get_logger("child")
    assert child.level == logging.NOTSET  # child has no own level, propagates


# ---------------------------------------------------------------------------
# Valid levels constant
# ---------------------------------------------------------------------------


def test_valid_levels_contains_standard() -> None:
    """_VALID_LEVELS includes all standard Python logging levels."""
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"):
        assert level in _VALID_LEVELS
