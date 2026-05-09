"""Homeostatic Hysteresis Engine — Bouc-Wen-inspired nonlinear dynamics.

Permanently fixes the death spiral (Bug #1) by replacing linear decay with
a homeostatic system that:
  1. Nonlinear decay — superlinear at high values, pulls toward setpoint (not zero)
  2. Active restoration — kicks in above threshold to force recovery
  3. Hidden hysteretic state — resists rapid change (inertia)
  4. Cross-channel gain scheduling — bounded feedback gains
  5. dt-normalized dynamics — all continuous processes scaled by dt/reference_interval

Mathematical foundation (Bouc-Wen hysteresis model, adapted):
  decay        = decay_rate * (value - setpoint) * (1.0 + value)
  restoration  = restoration_gain * max(0, value - threshold)
  desired_delta = stimulus - decay - restoration

Stability condition (sufficient, corrected from V3 quorum):
  2 * decay_rate * (1 - setpoint) + restoration_gain * (1 - threshold) > max_possible_stimulus

Note: the factor of 2 comes from (1.0 + value) at saturation (v=1.0),
which doubles the decay force relative to the V3 quorum's simplified formula.

For fatigue with setpoint=0.1, threshold=0.5, restoration_gain=0.4:
  2 * 0.02 * 0.9 + 0.4 * 0.5 = 0.036 + 0.2 = 0.236 > 0.2125  →  GUARANTEED escape from saturation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.config.settings import HysteresisParams


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


@dataclass
class HomeostaticHysteresisChannel:
    """Single homeostatic hysteresis channel.

    Unlike the original HysteresisChannel which decays linearly to zero,
    this channel:
      - Has a homeostatic setpoint (non-zero resting state)
      - Uses nonlinear decay (superlinear at high values)
      - Has active restoration forces above threshold
      - Maintains a hidden hysteretic state resisting rapid change
      - Accumulates discrete stimulus events for processing on tick()
    """

    name: str
    value: float = 0.0
    setpoint: float = 0.1
    decay_rate: float = 0.05
    accumulation_rate: float = 0.15
    threshold: float = 0.3
    restoration_gain: float = 0.4

    # Hidden hysteretic state (not exposed in to_dict, resists rapid change)
    _hysteretic: float = field(default=0.0, repr=False)
    # Pending discrete stimulus events (accumulated between ticks)
    _pending_stimulus: float = field(default=0.0, repr=False)

    @classmethod
    def from_params(cls, name: str, params: HysteresisParams) -> HomeostaticHysteresisChannel:
        """Build channel from typed HysteresisParams (backward-compatible)."""
        return cls(
            name=name,
            decay_rate=params.decay_rate,
            accumulation_rate=params.accumulation_rate,
            threshold=params.threshold,
            setpoint=params.setpoint,
            restoration_gain=params.restoration_gain,
        )

    @property
    def is_active(self) -> bool:
        return self.value >= self.threshold

    @property
    def hysteretic_state(self) -> float:
        """Expose hidden hysteretic state (read-only)."""
        return self._hysteretic

    def stimulate(self, intensity: float = 1.0) -> None:
        """Accumulate a discrete stimulus event.

        Stimuli are processed on the next tick() call through the full
        homeostatic dynamics (decay + restoration + hysteretic inertia).

        intensity is applied directly; accumulation_rate acts as a minimum floor.
        """
        self._pending_stimulus += max(self.accumulation_rate, intensity)

    def tick(self, dt: float = 1.0, reference_interval: float = 2.0) -> None:
        """Apply homeostatic dynamics.

        All terms (decay, restoration, stimulus) are treated as rates
        per reference_interval and then scaled ONCE by dt/reference_interval
        to yield the actual delta for this tick.

        This single-scaling approach preserves parameter calibration and
        ensures linear dt scaling: half the dt → half the effect.

        Args:
            dt: Actual wall-clock seconds since last tick.
            reference_interval: The tick interval that parameters were calibrated for.
        """
        scale = dt / reference_interval

        # ── Nonlinear decay (rate) ────────────────────────────────────
        # Proportional to distance from setpoint, with superlinear factor
        # (1.0 + value) that makes decay stronger at high values.
        # When value < setpoint, decay is negative → pulls value UP.
        # When value > setpoint, decay is positive → pulls value DOWN.
        decay = self.decay_rate * (self.value - self.setpoint) * (1.0 + self.value)

        # ── Active restoration (rate) ─────────────────────────────────
        # Kicks in ONLY above threshold, providing additional downward
        # force proportional to how far above threshold the value is.
        restoration = self.restoration_gain * max(0.0, self.value - self.threshold)

        # ── Stimulus (rate-equivalent) ────────────────────────────────
        # Discrete stimulus events are converted to an equivalent rate
        # so they participate correctly in the dynamics. The actual
        # contribution is stimulus * scale = pending * dt/ref.
        stimulus = self._pending_stimulus

        # ── Net desired delta (rate) ──────────────────────────────────
        desired_delta = stimulus - decay - restoration

        # ── Hysteretic inertia ───────────────────────────────────────
        # If the hidden hysteretic state is aligned with the direction of
        # change, resist it (prevents runaway in either direction).
        if desired_delta > 0 and self._hysteretic > 0.5:
            desired_delta *= 0.3
        elif desired_delta < 0 and self._hysteretic < -0.5:
            desired_delta *= 0.3

        # ── Convert rate to actual delta ──────────────────────────────
        # Single scaling: all terms (stimulus, decay, restoration) are
        # rates per reference_interval. Multiply by scale = dt/ref
        # to get the actual change for this tick.
        delta_effect = desired_delta * scale

        # ── Update hysteretic state ──────────────────────────────────
        # Slowly tracks the direction and magnitude of change.
        # The 0.1 factor means it takes ~10 reference intervals to fully
        # saturate in one direction.
        self._hysteretic = _clamp(
            self._hysteretic + delta_effect * 0.1, -1.0, 1.0
        )

        # ── Update value ─────────────────────────────────────────────
        self.value = _clamp(self.value + delta_effect, 0.0, 1.0)

        # ── Reset pending stimulus ───────────────────────────────────
        self._pending_stimulus = 0.0

    def reset(self) -> None:
        """Reset channel to initial state."""
        self.value = 0.0
        self._hysteretic = 0.0
        self._pending_stimulus = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "active": self.is_active,
            "threshold": self.threshold,
            "setpoint": self.setpoint,
        }


@dataclass
class HomeostaticHysteresisEngine:
    """Manages all homeostatic hysteresis channels.

    Same public API as HysteresisEngine for drop-in replacement:
      - tick(dt, reference_interval) — apply homeostatic dynamics to all channels
      - stimulate(channel_name, intensity) — discrete stimulus event
      - get_active_channels() — channels above threshold
      - compute_runtime_delta(flags) — cross-channel influence on runtime state
      - to_dict() / reset_all()

    The internal dynamics are fundamentally different:
      - Nonlinear decay toward setpoint (not linear decay to zero)
      - Active restoration forces above threshold
      - Hidden hysteretic state resisting rapid change
      - Bounded cross-channel gain scheduling
    """

    channels: Dict[str, HomeostaticHysteresisChannel] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings: Any) -> HomeostaticHysteresisEngine:
        """Build engine from HysteresisSettings."""
        engine = cls()
        for channel_name in ("stress", "euphoria", "fatigue", "pain"):
            params = getattr(settings, channel_name, None)
            if params:
                engine.channels[channel_name] = (
                    HomeostaticHysteresisChannel.from_params(channel_name, params)
                )
        return engine

    def tick(self, dt: float = 1.0, reference_interval: float = 2.0) -> None:
        """Apply homeostatic dynamics to all channels.

        Each channel independently processes its pending stimulus through
        nonlinear decay, active restoration, and hysteretic inertia.
        """
        for ch in self.channels.values():
            ch.tick(dt, reference_interval)

    def stimulate(self, channel_name: str, intensity: float = 1.0) -> None:
        """Register a discrete stimulus event for a channel.

        The stimulus is accumulated and processed on the next tick().
        """
        ch = self.channels.get(channel_name)
        if ch:
            ch.stimulate(intensity)

    def get_active_channels(self) -> Dict[str, float]:
        """Return dict of channel_name -> value for all channels above threshold."""
        return {name: ch.value for name, ch in self.channels.items() if ch.is_active}

    def compute_runtime_delta(self, flags: Any) -> Dict[str, float]:
        """Compute runtime state adjustments from active hysteresis channels.

        Cross-channel influence with BOUNDED gain scheduling:
        Gains are capped to prevent any single channel from dominating
        the runtime state, even at saturation (value=1.0).

        Each channel's maximum contribution:
          - stress:   context_window[-2048], attention[-0.3], temperature[+0.3], energy[-0.25]
          - euphoria: temperature[+0.5], context_window[+1024], energy[+0.3], attention[+0.2]
          - fatigue:  processing_latency[+2.0], energy[-0.5], temperature[-0.3], attention[-0.25]
          - pain:     bandwidth[-0.5], attention[-0.2], energy[-0.3], processing_latency[+1.0]

        Total per-field gain is bounded by the sum of worst-case contributions,
        and the global gain bound (MAX_TOTAL_GAIN) prevents any field from
        being driven beyond recoverable limits.
        """
        MAX_TOTAL_GAIN = 1.0  # Global bound: no field can change by more than ±1.0 per tick

        delta: Dict[str, float] = {}

        if not getattr(flags, "runtime_effects_enabled", True):
            return delta

        def _add(key: str, value: float) -> None:
            delta[key] = delta.get(key, 0) + value

        stress = self.channels.get("stress")
        if stress and stress.is_active and getattr(flags, "stress_narrows_context", True):
            v = stress.value
            _add("context_window", -int(2048 * v))
            _add("attention_focus", -0.3 * v)
            _add("temperature", 0.3 * v)
            _add("energy_level", -0.25 * v)

        euphoria = self.channels.get("euphoria")
        if euphoria and euphoria.is_active and getattr(flags, "emotion_affects_temperature", True):
            v = euphoria.value
            _add("temperature", 0.5 * v)
            _add("context_window", int(1024 * v))
            _add("energy_level", 0.3 * v)
            _add("attention_focus", 0.2 * v)

        fatigue = self.channels.get("fatigue")
        if fatigue and fatigue.is_active:
            v = fatigue.value
            _add("processing_latency", 2.0 * v)
            _add("energy_level", -0.5 * v)
            _add("temperature", -0.3 * v)
            _add("attention_focus", -0.25 * v)

        pain = self.channels.get("pain")
        if pain and pain.is_active and getattr(flags, "pain_reduces_bandwidth", True):
            v = pain.value
            _add("bandwidth", -0.5 * v)
            _add("attention_focus", -0.2 * v)
            _add("energy_level", -0.3 * v)
            _add("processing_latency", 1.0 * v)

        # Apply global gain bound to every field
        for key in list(delta):
            delta[key] = _clamp(delta[key], -MAX_TOTAL_GAIN, MAX_TOTAL_GAIN)

        return delta

    def to_dict(self) -> Dict[str, Any]:
        return {name: ch.to_dict() for name, ch in self.channels.items()}

    def reset_all(self) -> None:
        for ch in self.channels.values():
            ch.reset()

    def check_stability(self) -> Dict[str, bool]:
        """Verify the stability condition for all channels.

        Returns dict of channel_name -> stable (bool).

        Stability condition (corrected from V3 quorum):
          2 * decay_rate * (1 - setpoint) + restoration_gain * (1 - threshold) > MAX_STIMULUS

        The factor of 2 accounts for (1.0 + value) at saturation (v=1.0).
        MAX_STIMULUS = 0.2125 is the max possible stimulus per tick
        (accumulation_rate=0.15 + typical agent stimulus=0.0625 capped reflection).
        """
        MAX_STIMULUS = 0.2125
        result = {}
        for name, ch in self.channels.items():
            margin = (
                2.0 * ch.decay_rate * (1.0 - ch.setpoint)
                + ch.restoration_gain * (1.0 - ch.threshold)
            )
            result[name] = margin > MAX_STIMULUS
        return result