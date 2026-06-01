"""Tests for core.metrics — append-only with daily rotation."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.core.metrics import (
    MetricsLogger,
    get_current_metrics,
    record_metric,
)


@pytest.fixture
def tmp_metrics_path(tmp_path: Path) -> Path:
    return tmp_path / "metrics.jsonl"


class TestMetricsLogger:
    async def test_worker_logs_write_errors(self, tmp_metrics_path: Path) -> None:
        """_worker must log errors instead of swallowing."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()

        log_mock = MagicMock()
        logger._logger = log_mock

        mock_file = AsyncMock()
        mock_file.write.side_effect = OSError("disk full")
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_file)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "ai_assistant.core.metrics.aiofiles.open", return_value=mock_cm
        ):
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
        """Happy path: logged metrics are written to rotated file."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()
        logger.log({"endpoint": "/health", "latency_ms": 42})
        await logger.stop()

        rotated = list(
            tmp_metrics_path.parent.glob(f"{tmp_metrics_path.stem}-*.jsonl")
        )
        assert len(rotated) == 1
        raw = await asyncio.to_thread(rotated[0].read_text, encoding="utf-8")
        lines = raw.strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["endpoint"] == "/health"
        assert data["latency_ms"] == 42

    async def test_append_preserves_existing_lines(
        self, tmp_metrics_path: Path
    ) -> None:
        """Append must not overwrite prior metrics on the same day."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()
        logger.log({"event": "first"})
        await logger.stop()

        # Simulate restart with same file
        logger2 = MetricsLogger(path=str(tmp_metrics_path))
        logger2.start()
        logger2.log({"event": "second"})
        await logger2.stop()

        rotated = sorted(
            tmp_metrics_path.parent.glob(f"{tmp_metrics_path.stem}-*.jsonl")
        )
        assert len(rotated) == 1
        raw = await asyncio.to_thread(rotated[0].read_text, encoding="utf-8")
        lines = [line for line in raw.strip().split("\n") if line]
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "first"
        assert json.loads(lines[1])["event"] == "second"

    async def test_rotation_creates_new_file_next_day(
        self, tmp_metrics_path: Path
    ) -> None:
        """A new day must produce a new rotated file."""
        logger = MetricsLogger(path=str(tmp_metrics_path))
        logger.start()
        logger.log({"event": "day1"})
        await logger.stop()

        tomorrow = date.today() + timedelta(days=1)
        with patch("ai_assistant.core.metrics.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.date.return_value = tomorrow
            mock_dt.now.return_value = mock_now
            mock_dt.UTC = UTC

            logger2 = MetricsLogger(path=str(tmp_metrics_path))
            logger2.start()
            logger2.log({"event": "day2"})
            await logger2.stop()

        rotated = sorted(
            tmp_metrics_path.parent.glob(f"{tmp_metrics_path.stem}-*.jsonl")
        )
        assert len(rotated) == 2
        events = set()
        for r in rotated:
            raw = await asyncio.to_thread(r.read_text, encoding="utf-8")
            lines = [line for line in raw.strip().split("\n") if line]
            assert len(lines) == 1
            events.add(json.loads(lines[0])["event"])
        assert events == {"day1", "day2"}


@pytest.fixture(autouse=True)
def reset_request_metrics():
    """Reset ContextVar between tests to prevent cross-test pollution."""
    from ai_assistant.core.metrics import _request_metrics
    token = _request_metrics.set({})
    yield
    _request_metrics.reset(token)


class TestRecordMetric:
    def test_record_metric_context_var(self) -> None:
        record_metric("key", "value")
        metrics = get_current_metrics()
        assert "key" in metrics
        assert metrics["key"] == "value"

    def test_record_metric_rejects_invalid_type(self) -> None:
        """record_metric must reject non-JSON-serializable values immediately."""
        with pytest.raises(TypeError, match="JSON-serializable"):
            record_metric("bad", object())

    def test_get_current_metrics_returns_fresh_dict(self) -> None:
        """get_current_metrics() must return a fresh dict copy, never shared mutable."""
        record_metric("a", 1)
        m1 = get_current_metrics()
        m2 = get_current_metrics()
        assert m1 == {"a": 1}
        assert m2 == {"a": 1}
        assert m1 is not m2, "Returned the same mutable dict instance"
        m1["pollution"] = True
        assert "pollution" not in m2
        assert "pollution" not in get_current_metrics()
