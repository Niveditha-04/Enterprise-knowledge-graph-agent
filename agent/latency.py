"""Latency measurement helpers."""

from __future__ import annotations

import statistics
import time
from contextlib import contextmanager
from typing import Any, Iterator


@contextmanager
def measure_ms() -> Iterator[dict[str, float]]:
    record: dict[str, float] = {}
    start = time.perf_counter()
    yield record
    record["ms"] = (time.perf_counter() - start) * 1000


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_latencies(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"count": 0, "avg_ms": 0.0, "median_ms": 0.0, "p95_ms": 0.0}
    return {
        "count": len(samples),
        "avg_ms": statistics.mean(samples),
        "median_ms": statistics.median(samples),
        "p95_ms": percentile(samples, 95),
    }


def summarize_component_runs(runs: list[dict[str, Any]], component: str) -> dict[str, float]:
    values = [
        float(run["latency_ms"][component])
        for run in runs
        if run.get("latency_ms", {}).get(component) is not None
    ]
    return summarize_latencies(values)
