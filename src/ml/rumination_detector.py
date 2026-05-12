"""Entropy-based rumination detector.

Keeps a sliding window of categorical state labels (emotion names, thought
types, channel states, ...). Computes Shannon entropy over the window;
low entropy signals repetitive loops — a marker of "rumination" that
often precedes collapse.

Thresholds are in bits (natural log base is converted inside scipy):
    H ≥ info_threshold      → OK (diverse)
    warn_threshold ≤ H      → INFO
    crit_threshold ≤ H      → WARNING
    H < crit_threshold      → CRITICAL (deeply stuck)
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from math import log
from typing import Any, Deque, Dict

import structlog

from src.contracts.ml import (
    IRuminationDetector,
    RuminationSignal,
    WarningLevel,
)

logger = structlog.get_logger("consciousness.ml.rumination")


def _shannon_entropy(counts: Counter, base: float = 2.0) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for _, c in counts.items():
        if c <= 0:
            continue
        p = c / total
        h -= p * log(p, base)
    return h


@dataclass
class ShannonRuminationDetector:
    """`IRuminationDetector` via sliding-window Shannon entropy.

    Args:
        window_size: number of observations kept in the sliding window.
        warn_threshold: entropy above this is INFO.
        crit_threshold: entropy below this is CRITICAL.
        min_observations: no signal until window fills at least this far.
    """

    window_size: int = 30
    warn_threshold: float = 0.8  # bits
    crit_threshold: float = 0.3
    min_observations: int = 10
    _window: Deque[str] = field(default_factory=deque)

    def observe(self, state_label: str, tick: int) -> RuminationSignal:
        if len(self._window) >= self.window_size:
            self._window.popleft()
        self._window.append(state_label)

        if len(self._window) < self.min_observations:
            return RuminationSignal(
                level=WarningLevel.OK,
                entropy=float("nan"),
                window_size=len(self._window),
                unique_states=len(set(self._window)),
                rationale="window warming up",
            )

        counts = Counter(self._window)
        h = _shannon_entropy(counts)
        dominant = counts.most_common(1)[0][0] if counts else None

        if h < self.crit_threshold:
            level = WarningLevel.CRITICAL
        elif h < self.warn_threshold:
            level = WarningLevel.WARNING
        elif h < self.warn_threshold + 0.4:
            level = WarningLevel.INFO
        else:
            level = WarningLevel.OK

        signal = RuminationSignal(
            level=level,
            entropy=h,
            window_size=len(self._window),
            unique_states=len(counts),
            dominant_state=dominant,
            rationale=(
                f"entropy={h:.3f}, dominant={dominant!r} "
                f"({counts[dominant]}/{len(self._window)})"
                if dominant
                else f"entropy={h:.3f}"
            ),
        )
        if level in (WarningLevel.WARNING, WarningLevel.CRITICAL):
            logger.info(
                "rumination_signal",
                level=level.value,
                entropy=round(h, 3),
                dominant=dominant,
                tick=tick,
            )
        return signal

    def reset(self) -> None:
        self._window.clear()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "shannon",
            "window_size": self.window_size,
            "current_window": len(self._window),
            "warn_threshold": self.warn_threshold,
            "crit_threshold": self.crit_threshold,
        }


# Statically assert the implementation satisfies the contract.
_: IRuminationDetector = ShannonRuminationDetector()


__all__ = ["ShannonRuminationDetector"]
