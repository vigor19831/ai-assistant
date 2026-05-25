"""Tests for core.metrics — bare except fix validation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_assistant.core.metrics import (
    MetricsLogger,
    get_current_metrics,
    get_metrics_logger,
    record_metric,
)


@pytest.fixture
def tmp_metrics_path(tmp_path: Path) -> Path:
    return tmp_path / "metrics.jsonl"


class TestMetricsLogger:
    async def test_worker_logs_write_errors(self, tmp_metrics_path: Path) -> None:
        """Bare except fix: _worker must log errors instead of swallowing."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()

        log_mock = MagicMock()
        logger._logger = log_mock

        with patch.object(logger, "_append_line", side_effect=OSError("disk full")):
            logger.log({"event": "test"})
            await asyncio.sleep(0.15)
            await logger.stop()

        calls = [str(c.args) for c in log_mock.warning.call_args_list]
        assert any("disk full" in c for c in calls), (
            "Write error must be logged, not swallowed"
        )

    async def test_stop_logs_timeout(self, tmp_metrics_path: Path) -> None:
        """Bare except fix: stop must log timeout instead of swallowing."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()

        log_mock = MagicMock()
        logger._logger = log_mock
        real_task = logger._task

        with patch(
            "ai_assistant.core.metrics.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ):
            await logger.stop()

        calls = [str(c.args) for c in log_mock.warning.call_args_list]
        assert any("timed out" in c for c in calls), (
            "Timeout must be logged, not swallowed"
        )

        if real_task and not real_task.done():
            real_task.cancel()
            try:
                await real_task
            except asyncio.CancelledError:
                pass

    async def test_stop_logs_generic_error(self, tmp_metrics_path: Path) -> None:
        """Bare except fix: stop must log generic exceptions."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()

        log_mock = MagicMock()
        logger._logger = log_mock
        real_task = logger._task

        with patch(
            "ai_assistant.core.metrics.asyncio.wait_for",
            side_effect=RuntimeError("boom"),
        ):
            await logger.stop()

        calls = [str(c.args) for c in log_mock.warning.call_args_list]
        assert any("boom" in c for c in calls), (
            "Generic stop error must be logged, not swallowed"
        )

        if real_task and not real_task.done():
            real_task.cancel()
            try:
                await real_task
            except asyncio.CancelledError:
                pass

    async def test_log_and_read_back(self, tmp_metrics_path: Path) -> None:
        """Happy path: logged metrics are written to file."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()
        logger.log({"endpoint": "/health", "latency_ms": 42})
        await logger.stop()

        raw = await asyncio.to_thread(tmp_metrics_path.read_text, encoding="utf-8")
        lines = raw.strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["endpoint"] == "/health"
        assert data["latency_ms"] == 42

    def test_record_metric_context_var(self) -> None:
        record_metric("key", "value")
        metrics = get_current_metrics()
        assert "key" in metrics
        assert metrics["key"] == "value"

    def test_get_metrics_logger_singleton(self) -> None:
        a = get_metrics_logger()
        b = get_metrics_logger()
        assert a is b

    def test_get_current_metrics_outside_context_returns_fresh_empty_dict(self) -> None:
        """Outside a request context get_current_metrics() must return a fresh
        empty dict, never a shared mutable."""
        from ai_assistant.core.metrics import _request_metrics

        # Clear any existing token to simulate outside-context call
        token = _request_metrics.set(None)  # type: ignore[arg-type]
        try:
            m1 = get_current_metrics()
            m2 = get_current_metrics()
            assert m1 == {}
            assert m2 == {}
            assert m1 is not m2, "Returned the same mutable dict instance"
            m1["pollution"] = True
            assert "pollution" not in m2
            assert "pollution" not in get_current_metrics()
        finally:
            _request_metrics.reset(token)
