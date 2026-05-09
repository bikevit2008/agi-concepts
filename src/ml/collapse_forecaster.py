"""Critical Slowing Down (CSD) collapse forecaster.

Per-channel sliding-window statistics:
    - lag-1 autocorrelation (AR(1)) — rises before bifurcations
    - variance                    — rises as resilience decreases
    - linear trend slope on (ar1 + variance) — captures rate of change

When both AR(1) and variance trend upward simultaneously, the system is
approaching a tipping point. We raise warnings at configurable
thresholds.

Uses numpy (always available) with a pure-Python AR(1) estimate; if
statsmodels is importable, we prefer its implementation for rigor.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

import structlog

from src.contracts.ml import (
    CollapseSignal,
    ICollapseForecaster,
    WarningLevel,
)

logger = structlog.get_logger("consciousness.ml.collapse")


def _ar1(window: List[float]) -> float:
    """Lag-1 autocorrelation (Pearson) — 0.0 if undefined."""
    if len(window) < 2:
        return 0.0
    try:
        import numpy as np

        arr = np.asarray(window, dtype=float)
        if arr.std(ddof=0) < 1e-12:
            return 0.0
        x = arr[:-1]
        y = arr[1:]
        # Pearson correlation between x and y
        mx = x.mean()
        my = y.mean()
        num = ((x - mx) * (y - my)).sum()
        den = (((x - mx) ** 2).sum() ** 0.5) * (((y - my) ** 2).sum() ** 0.5)
        if den == 0:
            return 0.0
        return float(num / den)
    except ImportError:
        # Fall back to pure Python
        n = len(window)
        mean = sum(window) / n
        num = sum((window[i] - mean) * (window[i + 1] - mean) for i in range(n - 1))
        den = sum((x - mean) ** 2 for x in window)
        if den == 0:
            return 0.0
        return num / den


def _variance(window: List[float]) -> float:
    if len(window) < 2:
        return 0.0
    try:
        import numpy as np

        return float(np.var(window, ddof=0))
    except ImportError:
        mean = sum(window) / len(window)
        return sum((x - mean) ** 2 for x in window) / len(window)


def _linear_slope(series: List[float]) -> float:
    """OLS slope of `series` vs its index. Bounded and cheap."""
    if len(series) < 2:
        return 0.0
    n = len(series)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(series) / n
    num = sum((xs[i] - mx) * (series[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


@dataclass
class _ChannelState:
    window: Deque[float] = field(default_factory=deque)
    ar1_history: Deque[float] = field(default_factory=deque)
    var_history: Deque[float] = field(default_factory=deque)
    last_signal: Optional[CollapseSignal] = None


@dataclass
class CsdCollapseForecaster:
    """`ICollapseForecaster` using Critical Slowing Down indicators."""

    window_size: int = 50
    trend_history: int = 20
    ar1_warn_threshold: float = 0.6
    variance_warn_threshold: float = 0.1
    slope_warn_threshold: float = 0.01
    min_observations: int = 10
    _channels: Dict[str, _ChannelState] = field(default_factory=dict)

    def observe(self, channel: str, value: float, tick: int) -> CollapseSignal:
        state = self._channels.setdefault(channel, _ChannelState())
        if len(state.window) >= self.window_size:
            state.window.popleft()
        state.window.append(float(value))

        if len(state.window) < self.min_observations:
            signal = CollapseSignal(
                level=WarningLevel.OK,
                channel=channel,
                ar1=0.0,
                variance=0.0,
                trend_slope=0.0,
                rationale="warming up",
            )
            state.last_signal = signal
            return signal

        ar1 = _ar1(list(state.window))
        var = _variance(list(state.window))

        if len(state.ar1_history) >= self.trend_history:
            state.ar1_history.popleft()
        if len(state.var_history) >= self.trend_history:
            state.var_history.popleft()
        state.ar1_history.append(ar1)
        state.var_history.append(var)

        # Combined trend: average of ar1 and variance trend slopes
        slope_ar1 = _linear_slope(list(state.ar1_history))
        slope_var = _linear_slope(list(state.var_history))
        trend = (slope_ar1 + slope_var) / 2.0

        # Classify
        ar1_hot = ar1 >= self.ar1_warn_threshold
        var_hot = var >= self.variance_warn_threshold
        trend_hot = trend >= self.slope_warn_threshold

        if ar1_hot and var_hot and trend_hot:
            level = WarningLevel.CRITICAL
        elif ar1_hot and var_hot:
            level = WarningLevel.WARNING
        elif ar1_hot or var_hot or trend_hot:
            level = WarningLevel.INFO
        else:
            level = WarningLevel.OK

        signal = CollapseSignal(
            level=level,
            channel=channel,
            ar1=round(ar1, 4),
            variance=round(var, 4),
            trend_slope=round(trend, 6),
            rationale=(
                f"ar1={ar1:.3f} var={var:.3f} trend={trend:.4f}"
            ),
        )
        state.last_signal = signal

        if level in (WarningLevel.WARNING, WarningLevel.CRITICAL):
            logger.info(
                "collapse_signal",
                level=level.value,
                channel=channel,
                ar1=round(ar1, 3),
                variance=round(var, 3),
                trend=round(trend, 4),
                tick=tick,
            )
        return signal

    def latest(self, channel: Optional[str] = None) -> Optional[CollapseSignal]:
        if channel is not None:
            s = self._channels.get(channel)
            return s.last_signal if s else None
        # Return worst signal across channels
        signals = [s.last_signal for s in self._channels.values() if s.last_signal]
        if not signals:
            return None
        severity_order = {
            WarningLevel.CRITICAL: 3,
            WarningLevel.WARNING: 2,
            WarningLevel.INFO: 1,
            WarningLevel.OK: 0,
        }
        return max(signals, key=lambda s: severity_order.get(s.level, 0))

    def reset(self, channel: Optional[str] = None) -> None:
        if channel is None:
            self._channels.clear()
        else:
            self._channels.pop(channel, None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "csd",
            "window_size": self.window_size,
            "ar1_warn_threshold": self.ar1_warn_threshold,
            "variance_warn_threshold": self.variance_warn_threshold,
            "slope_warn_threshold": self.slope_warn_threshold,
            "channels": {
                name: {
                    "samples": len(s.window),
                    "last_level": s.last_signal.level.value if s.last_signal else None,
                }
                for name, s in self._channels.items()
            },
        }


# Statically assert the implementation satisfies the contract.
_: ICollapseForecaster = CsdCollapseForecaster()


__all__ = ["CsdCollapseForecaster"]
