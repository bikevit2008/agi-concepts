"""Saturation circuit breaker — detects sustained channel pinning.

Use case: a hysteresis channel (stress, fatigue, ...) gets pinned at or
near 1.0 for a sustained number of ticks. The homeostatic engine should
already pull it back via restoration_gain, but if math fails (numeric
edge cases, runaway feedback loop, model misconfiguration), we need an
externally-observable signal that the system is stuck.

The breaker tracks consecutive ticks above a saturation threshold per
channel. When the count exceeds `trip_after_ticks`, the channel is
"tripped" — downstream code can react (force_sleep, emergency reset,
alert, etc.).

Inspired by classic electrical-engineering circuit breakers, plus the
"sliding window error rate" pattern from the dify-search results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import structlog

from src.contracts.governance import ICircuitBreaker

logger = structlog.get_logger("consciousness.circuit_breaker")


@dataclass
class _ChannelState:
    """Internal counter for one channel."""

    consecutive_saturated: int = 0
    total_trips: int = 0
    last_trip_tick: Optional[int] = None
    is_tripped: bool = False


@dataclass
class SaturationCircuitBreaker:
    """Channel-level saturation detector.

    Configuration:
        saturation_threshold: value at/above which a channel is "saturated"
            (default 0.95 — channel at 1.0 ± numerical fuzz)
        trip_after_ticks: how many consecutive saturated ticks before tripping
            (default 50 — for 2s tick interval ≈ 100 seconds of pinning)
        reset_below: hysteresis-style reset threshold; channel must drop
            below this (default 0.7) before the trip clears

    The breaker is monotonic during a trip episode: once tripped, it stays
    tripped until value drops below `reset_below`.
    """

    saturation_threshold: float = 0.95
    trip_after_ticks: int = 50
    reset_below: float = 0.7
    _channels: Dict[str, _ChannelState] = field(default_factory=dict)

    def observe(self, channel: str, value: float, tick: int) -> bool:
        """Record current channel value. Returns True if NEWLY tripped."""
        state = self._channels.setdefault(channel, _ChannelState())

        # Already tripped — check for clearance
        if state.is_tripped:
            if value < self.reset_below:
                logger.info(
                    "circuit_breaker_cleared",
                    channel=channel,
                    value=round(value, 3),
                    tick=tick,
                )
                state.is_tripped = False
                state.consecutive_saturated = 0
            return False

        # Not tripped — check for saturation
        if value >= self.saturation_threshold:
            state.consecutive_saturated += 1
            if state.consecutive_saturated >= self.trip_after_ticks:
                state.is_tripped = True
                state.total_trips += 1
                state.last_trip_tick = tick
                logger.warning(
                    "circuit_breaker_tripped",
                    channel=channel,
                    value=round(value, 3),
                    consecutive=state.consecutive_saturated,
                    total_trips=state.total_trips,
                    tick=tick,
                )
                return True
        else:
            state.consecutive_saturated = 0
        return False

    def is_tripped(self, channel: Optional[str] = None) -> bool:
        if channel is None:
            return any(s.is_tripped for s in self._channels.values())
        s = self._channels.get(channel)
        return bool(s and s.is_tripped)

    def tripped_channels(self) -> List[str]:
        return [n for n, s in self._channels.items() if s.is_tripped]

    def reset(self, channel: Optional[str] = None) -> None:
        if channel is None:
            for s in self._channels.values():
                s.is_tripped = False
                s.consecutive_saturated = 0
            logger.info("circuit_breaker_reset_all")
        else:
            s = self._channels.get(channel)
            if s:
                s.is_tripped = False
                s.consecutive_saturated = 0
                logger.info("circuit_breaker_reset", channel=channel)

    def to_dict(self) -> Dict[str, object]:
        return {
            "type": "saturation",
            "saturation_threshold": self.saturation_threshold,
            "trip_after_ticks": self.trip_after_ticks,
            "reset_below": self.reset_below,
            "channels": {
                name: {
                    "consecutive_saturated": s.consecutive_saturated,
                    "total_trips": s.total_trips,
                    "last_trip_tick": s.last_trip_tick,
                    "is_tripped": s.is_tripped,
                }
                for name, s in self._channels.items()
            },
        }


# Statically assert the implementation satisfies the contract.
_: ICircuitBreaker = SaturationCircuitBreaker()
