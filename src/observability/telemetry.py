"""Telemetry - Lightweight structured metrics for pipeline monitoring

Collects latency, throughput, error rates, token usage, and per-stage
timing without heavyweight OTel dependencies.
"""
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import TELEMETRY_DIR

__all__ = [
    "MetricEntry",
    "TelemetryCollector",
    "reset_telemetry",
    "increment",
    "record",
    "start_timer",
    "stop_timer",
    "record_error",
    "get_report",
    "get_summary",
    "save_telemetry",
]


# =============================================================================
# METRICS
# =============================================================================

@dataclass
class MetricEntry:
    """A single metric sample.

    Attributes:
        name: Metric name.
        value: Sampled value.
        tags: Optional key-value tags.
        timestamp: Monotonic time of sampling.
    """
    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


class TelemetryCollector:
    """
    Singleton metrics collector.
    
    Supports:
    - Counters: increment-only (llm_calls, entities_extracted)
    - Histograms: distribution of values (latency_ms, tokens_per_call)
    - Gauges: current value (active_chunks, memory_mb)
    """

    _instance: "TelemetryCollector | None" = None

    def __new__(cls) -> "TelemetryCollector":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self.reset()

    def reset(self) -> None:
        """Reset all metrics. Call at the start of each pipeline run."""
        self._counters: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, float] = {}  # Active timers
        self._start_time = time.monotonic()
        self._errors: list[dict[str, Any]] = []

    # -- Counters --

    def increment(self, name: str, amount: float = 1.0) -> None:
        """Increment a counter by ``amount``.

        Args:
            name: Counter name.
            amount: Value to add (default 1).
        """
        self._counters[name] += amount

    def get_counter(self, name: str) -> float:
        return self._counters.get(name, 0.0)

    # -- Histograms --

    def record(self, name: str, value: float) -> None:
        """Append a value to a named histogram.

        Args:
            name: Histogram name.
            value: Value to record.
        """
        self._histograms[name].append(value)

    def get_histogram(self, name: str) -> dict:
        """Compute summary statistics for a histogram.

        Args:
            name: Histogram name.

        Returns:
            Dict with keys: count, min, max, mean, p50, p95, sum.
        """
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "p50": 0, "p95": 0}

        values_sorted = sorted(values)
        count = len(values_sorted)
        return {
            "count": count,
            "min": round(values_sorted[0], 2),
            "max": round(values_sorted[-1], 2),
            "mean": round(sum(values_sorted) / count, 2),
            "p50": round(values_sorted[count // 2], 2),
            "p95": round(values_sorted[int(count * 0.95)], 2) if count > 1 else round(values_sorted[0], 2),
            "sum": round(sum(values_sorted), 2),
        }

    # -- Gauges --

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge to a specific value.

        Args:
            name: Gauge name.
            value: Current value.
        """
        self._gauges[name] = value

    # -- Timers --

    def start_timer(self, name: str) -> None:
        """Start a named timer.

        Args:
            name: Timer name. Stopping this timer records a histogram
                entry under ``{name}_duration_ms``.
        """
        self._timers[name] = time.monotonic()

    def stop_timer(self, name: str) -> float:
        """Stop a named timer and record its duration.

        Args:
            name: Timer name previously passed to ``start_timer``.

        Returns:
            Elapsed time in milliseconds, or ``0.0`` if no timer was active.
        """
        start = self._timers.pop(name, None)
        if start is None:
            return 0.0
        duration_ms = (time.monotonic() - start) * 1000
        self.record(f"{name}_duration_ms", duration_ms)
        return duration_ms

    # -- Errors --

    def record_error(self, stage: str, error: str, fatal: bool = False) -> None:
        """Record an error occurrence.

        Args:
            stage: Pipeline stage where the error occurred.
            error: Error message.
            fatal: If True, also increments ``errors_fatal`` counter.
        """
        self._errors.append({
            "stage": stage,
            "error": error,
            "fatal": fatal,
            "timestamp": datetime.now().isoformat(),
        })
        self.increment("errors_total")
        if fatal:
            self.increment("errors_fatal")

    # -- Reports --

    def get_report(self) -> dict:
        """Build the full telemetry report.

        Returns:
            Dict with ``duration_s``, ``counters``, ``histograms``,
            ``gauges``, ``errors``, and ``error_count``.
        """
        total_duration = time.monotonic() - self._start_time

        return {
            "duration_s": round(total_duration, 2),
            "counters": dict(self._counters),
            "histograms": {
                name: self.get_histogram(name)
                for name in self._histograms
            },
            "gauges": dict(self._gauges),
            "errors": self._errors,
            "error_count": len(self._errors),
        }

    def get_summary(self) -> dict:
        """Build a concise summary suitable for embedding in output JSON.

        Returns:
            Dict with duration, LLM call count, token totals,
            entity/chunk counts, and error count.
        """
        report = self.get_report()
        return {
            "duration_s": report["duration_s"],
            "llm_calls": int(report["counters"].get("llm_calls", 0)),
            "tokens_prompt": int(report["counters"].get("tokens_prompt", 0)),
            "tokens_completion": int(report["counters"].get("tokens_completion", 0)),
            "entities_extracted": int(report["counters"].get("entities_extracted", 0)),
            "chunks_processed": int(report["counters"].get("chunks_processed", 0)),
            "errors": report["error_count"],
        }


# =============================================================================
# CONVENIENCE — Module-level functions
# =============================================================================

_collector = TelemetryCollector()


def reset_telemetry() -> None:
    """Reset all telemetry metrics for a new pipeline run."""
    _collector.reset()


def increment(name: str, amount: float = 1.0) -> None:
    """Increment a counter. See ``TelemetryCollector.increment``."""
    _collector.increment(name, amount)


def record(name: str, value: float) -> None:
    """Record a histogram value. See ``TelemetryCollector.record``."""
    _collector.record(name, value)


def start_timer(name: str) -> None:
    """Start a named timer. See ``TelemetryCollector.start_timer``."""
    _collector.start_timer(name)


def stop_timer(name: str) -> float:
    """Stop a named timer. See ``TelemetryCollector.stop_timer``."""
    return _collector.stop_timer(name)


def record_error(stage: str, error: str, fatal: bool = False) -> None:
    """Record an error. See ``TelemetryCollector.record_error``."""
    _collector.record_error(stage, error, fatal)


def get_report() -> dict:
    """Get full telemetry report. See ``TelemetryCollector.get_report``."""
    return _collector.get_report()


def get_summary() -> dict:
    """Get concise summary. See ``TelemetryCollector.get_summary``."""
    return _collector.get_summary()


def save_telemetry(trace_id: str | None = None) -> Path:
    """Save telemetry report to disk as JSON.

    Args:
        trace_id: Optional trace ID included in the filename.

    Returns:
        Path to the saved report file.
    """
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)

    suffix = f"_{trace_id}" if trace_id else ""
    report_path = TELEMETRY_DIR / f"telemetry{suffix}.json"

    with open(report_path, "w") as f:
        json.dump(_collector.get_report(), f, indent=2, default=str)

    print(f"📊 Telemetry saved: {report_path}")
    return report_path
