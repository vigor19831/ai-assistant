"""Tests for core/metrics.py — queue behavior, JSONL output, context isolation.

Validates MetricsLogger async queue, record_metric context vars, and edge cases.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from core.metrics import (
    MetricsLogger,
    get_current_metrics,
    get_metrics_logger,
    record_metric,
)

# ── MetricsLogger queue behavior ──


class TestMetricsLoggerQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_write(self):
        """Log entries should be written to JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            logger = MetricsLogger(str(path))
            logger.start()

            logger.log({"endpoint": "/test", "latency_ms": 42})
            logger.log({"endpoint": "/chat", "latency_ms": 100})

            # Give worker time to process
            await asyncio.sleep(0.1)
            await logger.stop()

            lines = path.read_text().strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["endpoint"] == "/test"
            assert json.loads(lines[1])["latency_ms"] == 100

    @pytest.mark.asyncio
    async def test_queue_full_drops_oldest(self):
        """QueueFull should silently drop new entries (not crash)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = MetricsLogger(str(Path(tmpdir) / "test_metrics.jsonl"))
            logger.start()

            # Fill queue beyond maxsize
            for _ in range(2000):
                logger.log({"data": "x" * 100})

            # Should not raise
            await logger.stop()

    @pytest.mark.asyncio
    async def test_stop_signals_worker(self):
        """stop() should signal worker to exit and flush remaining."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            logger = MetricsLogger(str(path))
            logger.start()

            logger.log({"test": "before_stop"})
            await logger.stop()

            # After stop, no new writes
            logger.log({"test": "after_stop"})

            content = path.read_text()
            lines = [line for line in content.strip().split("\n") if line]
            assert len(lines) == 1
            assert json.loads(lines[0])["test"] == "before_stop"

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """Multiple start() calls should not create multiple workers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = MetricsLogger(str(Path(tmpdir) / "test_metrics.jsonl"))
            logger.start()
            first_task = logger._task
            logger.start()
            assert logger._task is first_task
            await logger.stop()

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self):
        """Non-serializable objects should not crash the worker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            logger = MetricsLogger(str(path))
            logger.start()

            # default=str should handle non-serializable
            logger.log({"bytes": b"raw"})
            await asyncio.sleep(0.1)
            await logger.stop()

            lines = path.read_text().strip().split("\n")
            assert len(lines) == 1
            assert "raw" in lines[0]

    @pytest.mark.asyncio
    async def test_file_created_lazily(self):
        """File should not exist before first log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.jsonl"
            logger = MetricsLogger(str(path))
            assert not path.exists()
            logger.start()
            assert not path.exists()  # Still not created
            logger.log({"test": 1})
            await asyncio.sleep(0.1)
            assert path.exists()
            await logger.stop()


# ── ContextVar metrics ──


class TestRequestMetrics:
    def test_record_and_get(self):
        """record_metric should store in context, get_current_metrics \
        should retrieve."""
        record_metric("input_tokens", 100)
        record_metric("output_tokens", 50)
        metrics = get_current_metrics()
        assert metrics["input_tokens"] == 100
        assert metrics["output_tokens"] == 50

    def test_isolated_between_contexts(self):
        """Metrics should not leak between async contexts."""

        async def task_a():
            record_metric("task", "a")
            return get_current_metrics()

        async def task_b():
            record_metric("task", "b")
            return get_current_metrics()

        # Run in separate contexts
        m_a = asyncio.run(task_a())
        m_b = asyncio.run(task_b())

        assert m_a["task"] == "a"
        assert m_b["task"] == "b"

    def test_returns_empty_when_no_context(self):
        """Fresh context should return empty dict."""
        # Reset context
        import core.metrics

        core.metrics._request_metrics.set({})
        metrics = get_current_metrics()
        assert metrics == {}

    def test_returns_copy_not_reference(self):
        """get_current_metrics should return a copy."""
        record_metric("key", "value")
        m1 = get_current_metrics()
        m1["key"] = "modified"
        m2 = get_current_metrics()
        assert m2["key"] == "value"


# ── Singleton accessor ──


class TestGetMetricsLogger:
    def test_returns_same_instance(self):
        """get_metrics_logger should return singleton."""
        logger1 = get_metrics_logger()
        logger2 = get_metrics_logger()
        assert logger1 is logger2

    def test_creates_default_instance(self):
        """First call should create instance with default path."""
        with patch("core.metrics._metrics_logger", None):
            logger = get_metrics_logger()
            assert logger._path.name == "metrics.jsonl"
