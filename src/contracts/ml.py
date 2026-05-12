"""Contracts for ML-based regulators — rumination, collapse forecast, recovery.

These are optional tools that observe the system's time-series and warn
or act before a hard failure. They must NEVER interfere with the main
control loop (governance + circuit breaker stay authoritative). They
only provide signals.

Three contracts:

1. IRuminationDetector — monitors a stream of categorical states
   (thoughts, emotions) and flags when entropy drops below a threshold,
   indicating the system is stuck in a repetitive loop.

2. ICollapseForecaster — monitors continuous time-series (hysteresis
   channel values, runtime_state parameters) and flags early-warning
   signatures (rising AR(1), rising variance — Critical Slowing Down).

3. IRecoveryPolicy — given a warning signal, proposes a discrete action
   (force_sleep, reduce_temperature, inject_calm, etc.). Deterministic
   for MVP; later can be replaced with RL policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class WarningLevel(str, Enum):
    """Severity of an ML warning."""

    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class RuminationSignal:
    """Snapshot from the rumination detector."""

    level: WarningLevel
    entropy: float
    window_size: int
    unique_states: int
    dominant_state: Optional[str] = None
    rationale: str = ""


@dataclass
class CollapseSignal:
    """Snapshot from the collapse forecaster."""

    level: WarningLevel
    channel: str
    ar1: float  # lag-1 autocorrelation on the window
    variance: float
    trend_slope: float  # rolling slope of (ar1 + variance)
    rationale: str = ""


class RecoveryAction(str, Enum):
    """Discrete actions the recovery policy may propose."""

    NONE = "none"
    FORCE_SLEEP = "force_sleep"
    INJECT_CALM = "inject_calm"  # negative stimulation on stress
    LOWER_TEMPERATURE = "lower_temperature"
    RESET_CHANNEL = "reset_channel"
    ALERT_ONLY = "alert_only"


@dataclass
class RecoveryDecision:
    """Recovery policy output — what to do about a warning."""

    action: RecoveryAction
    target: Optional[str] = None  # channel/parameter the action applies to
    intensity: float = 0.0  # magnitude of the action
    rationale: str = ""


@runtime_checkable
class IRuminationDetector(Protocol):
    def observe(self, state_label: str, tick: int) -> RuminationSignal:
        """Append a state label, compute entropy, return a signal."""
        ...

    def reset(self) -> None: ...

    def to_dict(self) -> Dict[str, Any]: ...


@runtime_checkable
class ICollapseForecaster(Protocol):
    def observe(self, channel: str, value: float, tick: int) -> CollapseSignal:
        """Append a value, compute CSD indicators, return a signal."""
        ...

    def latest(self, channel: Optional[str] = None) -> Optional[CollapseSignal]:
        """Return the most recent signal for a channel (or worst)."""
        ...

    def reset(self, channel: Optional[str] = None) -> None: ...

    def to_dict(self) -> Dict[str, Any]: ...


@runtime_checkable
class IRecoveryPolicy(Protocol):
    def propose(
        self,
        rumination: Optional[RuminationSignal],
        collapse: List[CollapseSignal],
        runtime_state: Dict[str, float],
    ) -> RecoveryDecision:
        """Return a recovery action for the current signals."""
        ...

    def to_dict(self) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Null implementations
# ---------------------------------------------------------------------------


class NullRuminationDetector:
    def observe(self, state_label: str, tick: int) -> RuminationSignal:
        return RuminationSignal(
            level=WarningLevel.OK,
            entropy=float("nan"),
            window_size=0,
            unique_states=0,
            rationale="null",
        )

    def reset(self) -> None:
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "null"}


class NullCollapseForecaster:
    def observe(self, channel: str, value: float, tick: int) -> CollapseSignal:
        return CollapseSignal(
            level=WarningLevel.OK,
            channel=channel,
            ar1=0.0,
            variance=0.0,
            trend_slope=0.0,
            rationale="null",
        )

    def latest(self, channel: Optional[str] = None) -> Optional[CollapseSignal]:
        return None

    def reset(self, channel: Optional[str] = None) -> None:
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "null"}


class NullRecoveryPolicy:
    def propose(
        self,
        rumination: Optional[RuminationSignal],
        collapse: List[CollapseSignal],
        runtime_state: Dict[str, float],
    ) -> RecoveryDecision:
        return RecoveryDecision(action=RecoveryAction.NONE, rationale="null")

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "null"}
