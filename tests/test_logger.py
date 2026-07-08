"""Tests for core/logger.py — structured logging setup."""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any

import pytest

from ai_assistant.core.logger import get_logger, setup_logging

ROOT_LOGGER_NAME = "ai_assistant"


# ---------------------------------------------------------------------------
# Isolation fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_logger_state() -> None:
    """Save and restore ai_assistant logger state to prevent cross-test leaks."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    old_level = logger.level
    old_handlers = list(logger.handlers)
    old_propagate = logger.propagate

    yield

    logger.setLevel(old_level)
    logger.propagate = old_propagate
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        h.close()
    for h in old_handlers:
        logger.addHandler(h)


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_returns_logger(tmp_path: Path) -> None:
    """setup_logging returns the ai_assistant root logger."""
    log_file = tmp_path / "test.log"
    logger = setup_logging(level="DEBUG", log_file=str(log_file), fmt="text")
    assert logger.name == ROOT_LOGGER_NAME
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
    """Repeated calls remove old handlers and close file streams."""
    log_file = tmp_path / "reconfig.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="text")
    old_handlers = list(logger.handlers)
    old_file_handlers = [
        h for h in old_handlers if isinstance(h, logging.FileHandler)
    ]

    setup_logging(level="DEBUG", log_file=str(log_file), fmt="json")

    # Old handlers removed from logger
    for h in old_handlers:
        assert h not in logger.handlers

    # Old file handler streams closed to prevent fd leaks
    for h in old_file_handlers:
        assert h.stream is None

    assert logger.level == logging.DEBUG


def test_setup_logging_console_only() -> None:
    """log_file=None produces only console handlers."""
    logger = setup_logging(level="INFO", log_file=None, fmt="text")
    assert all(not isinstance(h, logging.FileHandler) for h in logger.handlers)


def test_setup_logging_file_handler_created(tmp_path: Path) -> None:
    """log_file set creates RotatingFileHandler."""
    log_file = tmp_path / "file.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="text")
    file_handlers = [
        h for h in logger.handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1


def test_setup_logging_file_write(tmp_path: Path) -> None:
    """Log messages are written to the file."""
    log_file = tmp_path / "write.log"
    logger = setup_logging(level="INFO", log_file=str(log_file), fmt="text")
    logger.info("file test message")
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


def test_setup_logging_oserror_on_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """OSError on file creation falls back to console, does not crash."""
    def _raise(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("ai_assistant.core.logger.Path.mkdir", _raise)
    logger = setup_logging(
        level="INFO", log_file="/tmp/fake/sub/test.log", fmt="text"
    )
    assert logger.name == ROOT_LOGGER_NAME
    # Console handler still present as fallback
    assert any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )


# ---------------------------------------------------------------------------
# Text format (via public API)
# ---------------------------------------------------------------------------


def _capture(capsys: pytest.CaptureFixture) -> str:
    """Return combined stdout + stderr capture, safe for StreamHandler defaults."""
    captured = capsys.readouterr()
    return captured.out + captured.err


def test_text_format_basic(capsys: pytest.CaptureFixture) -> None:
    """Text formatter produces expected line without trace_id."""
    logger = setup_logging(level="INFO", log_file=None, fmt="text")
    logger.info("basic message")
    output = _capture(capsys)
    assert "INFO" in output
    assert "basic message" in output
    assert "trace_id=" not in output


def test_text_format_with_trace_id(capsys: pytest.CaptureFixture) -> None:
    """Text formatter includes trace_id when present."""
    logger = setup_logging(level="INFO", log_file=None, fmt="text")
    logger.info("traced", extra={"trace_id": "abc123"})
    output = _capture(capsys)
    assert "trace_id=abc123" in output
    assert "traced" in output


# ---------------------------------------------------------------------------
# JSON format (via public API)
# ---------------------------------------------------------------------------


def test_json_format_basic(capsys: pytest.CaptureFixture) -> None:
    """JSON formatter produces valid JSON with required fields."""
    logger = setup_logging(level="INFO", log_file=None, fmt="json")
    logger.info("json test")
    output = _capture(capsys)
    parsed = json.loads(output.strip().split("\n")[0])
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "json test"
    assert parsed["logger"] == ROOT_LOGGER_NAME
    assert "timestamp" in parsed


def test_json_format_with_trace_id(capsys: pytest.CaptureFixture) -> None:
    """JSON formatter includes trace_id as top-level field."""
    logger = setup_logging(level="INFO", log_file=None, fmt="json")
    logger.info("traced", extra={"trace_id": "xyz789"})
    output = _capture(capsys)
    parsed = json.loads(output.strip().split("\n")[0])
    assert parsed["trace_id"] == "xyz789"


def test_json_format_extra_fields(capsys: pytest.CaptureFixture) -> None:
    """JSON formatter captures custom extra fields."""
    logger = setup_logging(level="INFO", log_file=None, fmt="json")
    logger.info("extra", extra={"custom_field": "custom_value"})
    output = _capture(capsys)
    parsed = json.loads(output.strip().split("\n")[0])
    assert parsed["custom_field"] == "custom_value"


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


def test_get_logger_returns_child() -> None:
    """get_logger returns a child of ai_assistant."""
    logger = get_logger("test_module")
    assert logger.name == f"{ROOT_LOGGER_NAME}.test_module"


def test_get_logger_propagates_level() -> None:
    """Child logger inherits level from parent."""
    setup_logging(level="WARNING", log_file=None, fmt="text")
    child = get_logger("child")
    assert child.level == logging.NOTSET  # child has no own level, propagates
