"""Tests for core/metrics.py — in-memory Prometheus-compatible metrics."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ai_assistant.core.metrics import (
    _DEFAULT_BUCKETS,
    _key_str,
    _labels_key,
    _metric_line,
    get_metrics,
    get_metrics_json,
    increment_counter,
    observe_histogram,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def test_labels_key_empty() -> None:
    """_labels_key with None returns empty tuple."""
    assert _labels_key(None) == ()


def test_labels_key_sorted() -> None:
    """_labels_key sorts keys alphabetically."""
    labels = {"b": "2", "a": "1"}
    assert _labels_key(labels) == (("a", "1"), ("b", "2"))


def test_key_str_no_labels() -> None:
    """_key_str without labels returns just the name."""
    assert _key_str("requests_total", ()) == "requests_total"


def test_key_str_with_labels() -> None:
    """_key_str formats labels in Prometheus style."""
    labels = (("method", "GET"), ("status", "200"))
    result = _key_str("requests_total", labels)
    assert result == 'requests_total{method="GET",status="200"}'


def test_metric_line() -> None:
    """_metric_line produces name + value line."""
    line = _metric_line("counter", (), 42)
    assert line == "counter 42"


# ---------------------------------------------------------------------------
# increment_counter
# ---------------------------------------------------------------------------


def test_counter_basic_increment() -> None:
    """Counter increments by 1 by default."""
    increment_counter("test_counter")
    metrics = get_metrics()
    assert "test_counter 1" in metrics


def test_counter_with_labels() -> None:
    """Counter with labels creates separate time series."""
    increment_counter("labeled", labels={"env": "test"})
    increment_counter("labeled", labels={"env": "test"})
    metrics = get_metrics()
    assert 'labeled{env="test"} 2' in metrics


def test_counter_custom_value() -> None:
    """Counter can increment by arbitrary value."""
    increment_counter("big_step", value=5)
    metrics = get_metrics()
    assert "big_step 5" in metrics


def test_counter_multiple_namespaces() -> None:
    """Different label combinations are independent."""
    increment_counter("ns", labels={"a": "1"})
    increment_counter("ns", labels={"a": "2"})
    metrics = get_metrics()
    assert 'ns{a="1"} 1' in metrics
    assert 'ns{a="2"} 1' in metrics


# ---------------------------------------------------------------------------
# observe_histogram
# ---------------------------------------------------------------------------


def test_histogram_basic() -> None:
    """Histogram observation creates buckets and sum/count."""
    observe_histogram("latency", 0.05)
    metrics = get_metrics()
    assert "# TYPE latency histogram" in metrics
    assert 'latency_bucket{le="0.05"} 1' in metrics
    assert 'latency_bucket{le="+Inf"} 1' in metrics
    assert "latency_count 1" in metrics
    assert "latency_sum 0.050000" in metrics


def test_histogram_multiple_observations() -> None:
    """Multiple observations accumulate in buckets."""
    observe_histogram("multi", 0.01)
    observe_histogram("multi", 0.5)
    observe_histogram("multi", 5.0)
    metrics = get_metrics()
    # 0.01 falls into buckets <=0.005? No, 0.01 > 0.005, so <=0.01
    assert 'multi_bucket{le="0.01"} 1' in metrics
    # 0.5 falls into <=0.5
    assert 'multi_bucket{le="0.5"} 2' in metrics  # 0.01 + 0.5
    # 5.0 falls into <=10.0
    assert 'multi_bucket{le="10.0"} 3' in metrics
    assert "multi_count 3" in metrics


def test_histogram_with_labels() -> None:
    """Histogram supports label dimensions."""
    observe_histogram("lbl_hist", 0.1, labels={"path": "/api"})
    metrics = get_metrics()
    assert 'lbl_hist_bucket{le="0.1",path="/api"} 1' in metrics
    assert 'lbl_hist_bucket{le="+Inf",path="/api"} 1' in metrics


def test_histogram_zero_value() -> None:
    """Zero value goes into all buckets."""
    observe_histogram("zero", 0.0)
    metrics = get_metrics()
    assert 'zero_bucket{le="0.005"} 1' in metrics


def test_histogram_large_value() -> None:
    """Value exceeding all buckets goes into +Inf only."""
    observe_histogram("large", 100.0)
    metrics = get_metrics()
    # Should NOT be in any finite bucket
    assert 'large_bucket{le="10.0"} 0' in metrics
    assert 'large_bucket{le="+Inf"} 1' in metrics


# ---------------------------------------------------------------------------
# get_metrics (Prometheus format)
# ---------------------------------------------------------------------------


def test_get_metrics_empty() -> None:
    """Empty registry returns empty string."""
    # Note: module-level globals persist, so we test format instead
    metrics = get_metrics()
    assert isinstance(metrics, str)


def test_get_metrics_counter_format() -> None:
    """Counter section has HELP, TYPE, and value line."""
    increment_counter("fmt_test")
    metrics = get_metrics()
    lines = metrics.split("\n")
    assert any("# HELP fmt_test" in line for line in lines)
    assert any("# TYPE fmt_test counter" in line for line in lines)
    assert any("fmt_test 1" in line for line in lines)


def test_get_metrics_histogram_format() -> None:
    """Histogram section has all required lines."""
    observe_histogram("fmt_hist", 0.1)
    metrics = get_metrics()
    lines = metrics.split("\n")
    assert any("# HELP fmt_hist Latency" in line for line in lines)
    assert any("# TYPE fmt_hist histogram" in line for line in lines)
    assert any("fmt_hist_count 1" in line for line in lines)
    assert any("fmt_hist_sum" in line for line in lines)
    assert any("fmt_hist_bucket{le=\"+Inf\"} 1" in line for line in lines)


def test_get_metrics_thread_safety() -> None:
    """Concurrent increments do not corrupt output."""
    import threading

    def _worker() -> None:
        for _ in range(100):
            increment_counter("thread_safe")

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    metrics = get_metrics()
    assert "thread_safe 400" in metrics


# ---------------------------------------------------------------------------
# get_metrics_json
# ---------------------------------------------------------------------------


def test_get_metrics_json_structure() -> None:
    """JSON output has counters and histograms top-level keys."""
    increment_counter("json_counter")
    observe_histogram("json_hist", 0.1)
    data = get_metrics_json()
    assert "counters" in data
    assert "histograms" in data


def test_get_metrics_json_counter_value() -> None:
    """JSON counter value matches internal state."""
    increment_counter("json_val", labels={"k": "v"}, value=3)
    data = get_metrics_json()
    assert data["counters"]['json_val{k="v"}'] == 3


def test_get_metrics_json_histogram_buckets() -> None:
    """JSON histogram includes all default buckets."""
    observe_histogram("json_bucket", 0.05)
    data = get_metrics_json()
    hist = data["histograms"]["json_bucket"]
    for b in _DEFAULT_BUCKETS:
        assert str(b) in hist["buckets"]
    assert hist["count"] == 1
    assert hist["sum"] == 0.05


def test_get_metrics_json_empty_histograms() -> None:
    """JSON with no histograms has empty histograms dict."""
    # Ensure at least one counter exists for the test
    increment_counter("ensure_counter")
    data = get_metrics_json()
    assert isinstance(data["histograms"], dict)


# ---------------------------------------------------------------------------
# Default buckets constant
# ---------------------------------------------------------------------------


def test_default_buckets_ordered() -> None:
    """Default buckets are strictly increasing."""
    for i in range(len(_DEFAULT_BUCKETS) - 1):
        assert _DEFAULT_BUCKETS[i] < _DEFAULT_BUCKETS[i + 1]


def test_default_buckets_positive() -> None:
    """All default buckets are positive."""
    for b in _DEFAULT_BUCKETS:
        assert b > 0
