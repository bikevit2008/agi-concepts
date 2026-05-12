"""Circadian oscillator + Two-Process Model of sleep regulation.

Implements an analog of:
- Process S (homeostatic sleep pressure): builds up while awake,
  dissipates while asleep. Bounded [0, 1].
- Process C (circadian alerting signal): a sinusoid with period 24h
  (configurable). Peaks "evening", troughs "morning".

Decision:
    pressure_to_sleep = S - C   (bigger → "more like sleep")
    pressure_to_wake  = C - S

If pressure_to_sleep crosses `pressure_to_sleep_threshold`, transition
AWAKE → DROWSY → SLEEPING. If pressure_to_wake crosses
`pressure_to_wake_threshold` while sleeping, transition back to AWAKE.

When asleep, the manager alternates NREM ↔ REM phases at a configurable
fraction (default 70% NREM, 30% REM, mirrors human sleep architecture).

Pure-Python; no scipy needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional

import structlog

from src.contracts.sleep import (
    SleepDecision,
    SleepPhase,
    WakeState,
)

logger = structlog.get_logger("consciousness.engine.circadian")


@dataclass
class CircadianConfig:
    """Tunable parameters for the Two-Process Model."""

    awake_seconds: float = 4 * 3600.0   # 4 hours awake → S grows toward 1.0
    sleep_seconds: float = 1 * 3600.0   # 1 hour sleep  → S decays toward 0
    pressure_to_sleep_threshold: float = 0.7
    pressure_to_wake_threshold: float = 0.2
    nrem_fraction: float = 0.7  # 70% of sleep in NREM, 30% REM
    rem_cycle_seconds: float = 90 * 60.0  # ~90 min mammalian cycle
    suppress_llm_during_sleep: bool = True


@dataclass
class CircadianSleepManager:
    """Two-Process sleep regulator + NREM/REM phase clock."""

    config: CircadianConfig = field(default_factory=CircadianConfig)

    # State
    _wake_state: WakeState = WakeState.AWAKE
    _phase: SleepPhase = SleepPhase.NONE
    _process_s: float = 0.0   # 0..1 sleep pressure
    _process_c_phase: float = 0.0  # 0..1 of full circadian cycle
    _seconds_in_state: float = 0.0
    _seconds_in_phase: float = 0.0
    _last_decision: Optional[SleepDecision] = None
    _force_sleep: bool = False
    _force_wake: bool = False

    @property
    def _circadian_signal(self) -> float:
        """C ∈ [-1, +1]; +1 ~ evening, -1 ~ morning."""
        return math.sin(2 * math.pi * self._process_c_phase)

    def update(
        self,
        tick: int,
        dt_seconds: float,
        runtime_state: Dict[str, float],
        hysteresis_state: Dict[str, float],
    ) -> SleepDecision:
        if dt_seconds < 0:
            dt_seconds = 0.0

        # Process S — homeostatic, depends on wake/sleep
        if self._wake_state in (WakeState.AWAKE, WakeState.DROWSY):
            ds = dt_seconds / max(1.0, self.config.awake_seconds)
            self._process_s = min(1.0, self._process_s + ds)
        else:
            ds = dt_seconds / max(1.0, self.config.sleep_seconds)
            self._process_s = max(0.0, self._process_s - ds)

        # Process C — 24h cycle (using awake_seconds*~6 as full cycle for demo)
        full_cycle = self.config.awake_seconds + self.config.sleep_seconds
        if full_cycle > 0:
            self._process_c_phase = (
                self._process_c_phase + dt_seconds / (full_cycle * 5.0)
            ) % 1.0

        self._seconds_in_state += dt_seconds
        self._seconds_in_phase += dt_seconds

        c_signal = (self._circadian_signal + 1.0) / 2.0  # remap to [0, 1]

        # Combined pressures
        pressure_to_sleep = self._process_s - 0.3 * (1.0 - c_signal)
        pressure_to_wake = (1.0 - self._process_s) + 0.3 * c_signal - 0.5

        # External overrides
        if self._force_sleep:
            self._transition(WakeState.DROWSY, "force_sleep")
            self._force_sleep = False
        if self._force_wake:
            self._transition(WakeState.WAKING, "force_wake")
            self._force_wake = False

        # State machine
        if self._wake_state == WakeState.AWAKE:
            if pressure_to_sleep >= self.config.pressure_to_sleep_threshold:
                self._transition(WakeState.DROWSY, "pressure_to_sleep")
        elif self._wake_state == WakeState.DROWSY:
            # Brief transition; after a few seconds → SLEEPING
            if self._seconds_in_state > 5.0:
                self._transition(WakeState.SLEEPING, "drowsy_to_sleep")
                self._enter_phase(SleepPhase.NREM)
        elif self._wake_state == WakeState.SLEEPING:
            # NREM/REM cycling
            if self._seconds_in_phase > self.config.rem_cycle_seconds:
                if self._phase == SleepPhase.NREM:
                    self._enter_phase(SleepPhase.REM)
                else:
                    self._enter_phase(SleepPhase.NREM)
            # Wake check
            if pressure_to_wake >= self.config.pressure_to_wake_threshold:
                self._transition(WakeState.WAKING, "pressure_to_wake")
                self._enter_phase(SleepPhase.NONE)
        elif self._wake_state == WakeState.WAKING:
            if self._seconds_in_state > 5.0:
                self._transition(WakeState.AWAKE, "waking_done")

        suppress = (
            self.config.suppress_llm_during_sleep
            and self._wake_state in (WakeState.SLEEPING, WakeState.DROWSY, WakeState.WAKING)
        )

        decision = SleepDecision(
            wake_state=self._wake_state,
            phase=self._phase,
            sleep_pressure=round(self._process_s, 4),
            circadian_phase=round(self._process_c_phase, 4),
            suppress_llm_calls=suppress,
            rationale=f"S={self._process_s:.2f} C={c_signal:.2f}",
        )
        self._last_decision = decision
        return decision

    def _transition(self, new_state: WakeState, reason: str) -> None:
        if new_state == self._wake_state:
            return
        prev = self._wake_state
        self._wake_state = new_state
        self._seconds_in_state = 0.0
        logger.info(
            "sleep_transition",
            from_state=prev.value,
            to_state=new_state.value,
            reason=reason,
            sleep_pressure=round(self._process_s, 3),
        )

    def _enter_phase(self, new_phase: SleepPhase) -> None:
        if new_phase == self._phase:
            return
        prev = self._phase
        self._phase = new_phase
        self._seconds_in_phase = 0.0
        if new_phase != SleepPhase.NONE:
            logger.info("sleep_phase_change", from_phase=prev.value, to_phase=new_phase.value)

    def force_sleep(self) -> None:
        self._force_sleep = True

    def force_wake(self) -> None:
        self._force_wake = True

    def to_dict(self) -> Dict[str, object]:
        return {
            "type": "circadian_two_process",
            "wake_state": self._wake_state.value,
            "phase": self._phase.value,
            "process_s": round(self._process_s, 4),
            "process_c_phase": round(self._process_c_phase, 4),
            "seconds_in_state": round(self._seconds_in_state, 2),
            "config": {
                "awake_seconds": self.config.awake_seconds,
                "sleep_seconds": self.config.sleep_seconds,
                "pressure_to_sleep_threshold": self.config.pressure_to_sleep_threshold,
                "pressure_to_wake_threshold": self.config.pressure_to_wake_threshold,
                "suppress_llm_during_sleep": self.config.suppress_llm_during_sleep,
            },
        }


__all__ = ["CircadianConfig", "CircadianSleepManager"]
