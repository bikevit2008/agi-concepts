"""Metrics computed over HarnessResult traces.

Implements the key V3 metrics:
- MTTDS proxy: time_above_saturation(trace, threshold=0.95)
- Recovery time: measure_recovery_time(trace, from_tick, to_baseline)
- Death spiral detection: detect_death_spiral(trace, window, cap=0.95)
- Spiral count (how many times the trace was saturated)
"""

from __future__ import annotations

from typing import Dict, List, Optional


def time_above_saturation(
    trace: List[float],
    threshold: float = 0.95,
) -> int:
    """Return the number of ticks where value >= threshold."""
    return sum(1 for v in trace if v >= threshold)


def detect_death_spiral(
    trace: List[float],
    window: int = 50,
    threshold: float = 0.95,
) -> Optional[int]:
    """Find the first tick where `trace[t-window:t]` stays above threshold.

    Returns tick index (t) where the saturation lasts for `window`
    consecutive samples; None if no such window.
    """
    if len(trace) < window:
        return None
    for t in range(window, len(trace) + 1):
        if all(v >= threshold for v in trace[t - window : t]):
            return t
    return None


def spiral_count(
    trace: List[float],
    threshold: float = 0.95,
    min_length: int = 10,
) -> int:
    """Count distinct saturation episodes at least min_length long."""
    count = 0
    run = 0
    for v in trace:
        if v >= threshold:
            run += 1
        else:
            if run >= min_length:
                count += 1
            run = 0
    if run >= min_length:
        count += 1
    return count


def measure_recovery_time(
    trace: List[float],
    from_tick: int,
    to_baseline: float = 0.3,
    max_wait: Optional[int] = None,
) -> Optional[int]:
    """Ticks to drop below `to_baseline` starting from `from_tick`.

    Returns delta in ticks, or None if the series doesn't recover within
    `max_wait` (defaults to the remainder of the trace).
    """
    start = from_tick
    if start < 0 or start >= len(trace):
        return None
    stop = len(trace) if max_wait is None else min(len(trace), start + max_wait + 1)
    for i in range(start, stop):
        if trace[i] < to_baseline:
            return i - start
    return None


def summarize_run(channel_traces: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
    """Per-channel summary: max / mean / time_above / spiral_count."""
    out: Dict[str, Dict[str, float]] = {}
    for name, trace in channel_traces.items():
        if not trace:
            continue
        n = len(trace)
        out[name] = {
            "max": max(trace),
            "mean": sum(trace) / n,
            "time_above_0.95": time_above_saturation(trace, 0.95),
            "spiral_count": spiral_count(trace),
            "last": trace[-1],
        }
    return out


__all__ = [
    "detect_death_spiral",
    "measure_recovery_time",
    "spiral_count",
    "summarize_run",
    "time_above_saturation",
]
