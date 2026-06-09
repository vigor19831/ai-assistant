"""In-memory metrics registry — stdlib only, Prometheus-compatible."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

__all__ = [
    "get_metrics",
    "get_metrics_json",
    "increment_counter",
    "observe_histogram",
]

_DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_histograms: dict[
    tuple[str, tuple[tuple[str, str], ...]],
    dict[str, Any],
] = {}

_lock = threading.Lock()


def _labels_key(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((labels or {}).items()))


def _key_str(name: str, labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return name
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels))
    return f"{name}{{{label_str}}}"


def _metric_line(
    name: str,
    labels: tuple[tuple[str, str], ...],
    value: str | int | float,
) -> str:
    return f"{_key_str(name, labels)} {value}"


def increment_counter(
    name: str,
    labels: dict[str, str] | None = None,
    value: int = 1,
) -> None:
    """Increment a counter metric."""
    key = (name, _labels_key(labels))
    with _lock:
        _counters[key] += value


def observe_histogram(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Observe a value into a histogram."""
    key = (name, _labels_key(labels))
    with _lock:
        hist = _histograms.setdefault(
            key,
            {"buckets": defaultdict(int), "sum": 0.0, "count": 0},
        )
        for b in _DEFAULT_BUCKETS:
            if value <= b:
                hist["buckets"][b] += 1
        hist["sum"] += value
        hist["count"] += 1


def get_metrics() -> str:
    """Return metrics in Prometheus exposition format."""
    with _lock:
        lines: list[str] = []

        for (name, labels), value in _counters.items():
            lines.append(f"# HELP {name} Total")
            lines.append(f"# TYPE {name} counter")
            lines.append(_metric_line(name, labels, value))

        for (name, labels), hist in _histograms.items():
            lines.append(f"# HELP {name} Latency")
            lines.append(f"# TYPE {name} histogram")
            for b in _DEFAULT_BUCKETS:
                bucket_labels = labels + (("le", str(b)),)
                lines.append(
                    _metric_line(
                        f"{name}_bucket",
                        bucket_labels,
                        hist["buckets"].get(b, 0),
                    )
                )
            inf_labels = labels + (("le", "+Inf"),)
            lines.append(_metric_line(f"{name}_bucket", inf_labels, hist["count"]))
            lines.append(_metric_line(f"{name}_count", labels, hist["count"]))
            lines.append(_metric_line(f"{name}_sum", labels, f"{hist['sum']:.6f}"))

        return "\n".join(lines)


def get_metrics_json() -> dict[str, Any]:
    """Return metrics as a JSON-serializable dict."""
    with _lock:
        return {
            "counters": {
                _key_str(name, labels): value
                for (name, labels), value in _counters.items()
            },
            "histograms": {
                _key_str(name, labels): {
                    "buckets": {
                        str(b): hist["buckets"].get(b, 0) for b in _DEFAULT_BUCKETS
                    },
                    "count": hist["count"],
                    "sum": hist["sum"],
                }
                for (name, labels), hist in _histograms.items()
            },
        }
